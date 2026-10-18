"""Account-scoped correspondence across existing channels; no external synchronization."""
from collections import Counter
from datetime import datetime, timezone
import json
from typing import Literal

from fastapi import Depends, Query, HTTPException
from pydantic import BaseModel, StrictBool
from backend import mailing

SCHEMA = '''
CREATE TABLE IF NOT EXISTS message_center_read_state(
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_id TEXT NOT NULL, unread INTEGER NOT NULL,
    PRIMARY KEY(user_id,message_id));
'''


class ReadState(BaseModel):
    unread: StrictBool


def collect(con, current):
    rows = []

    def add(source, identifier, channel, direction, title, content, sender, recipient, created_at, **extra):
        rows.append({'id': f'{source}:{identifier}', 'source': source, 'source_id': identifier,
                     'channel': channel, 'direction': direction, 'title': title, 'content': content,
                     'sender': sender or '', 'recipient': recipient or '', 'created_at': created_at,
                     'status': '', 'unread': False, **extra})

    for row in con.execute('''SELECT id,sender_name,sender_email,recipient,subject,content,folder,unread,created_at
                              FROM client_mail WHERE user_id=? AND folder!='spam' AND category!='spam' ''', (current['id'],)):
        outgoing = row['folder'] in ('sent', 'drafts')
        unread = bool(row['unread'] and not outgoing)
        status = row['folder'] if row['folder'] in ('drafts', 'spam', 'trash') else ('sent' if outgoing else 'unread' if unread else 'read')
        add('email', row['id'], 'email', 'outgoing' if outgoing else 'incoming', row['subject'], row['content'],
            row['sender_name'] or row['sender_email'], row['recipient'], row['created_at'],
            status=status, unread=unread, folder=row['folder'], address=row['sender_email'])

    for row in con.execute('''SELECT m.*,s.name AS sender_name,r.name AS recipient_name FROM user_messages m
        JOIN users s ON s.id=m.sender_id JOIN users r ON r.id=m.recipient_id
        WHERE m.sender_id=? OR m.recipient_id=?''', (current['id'], current['id'])):
        outgoing = row['sender_id'] == current['id'] and row['recipient_id'] != current['id']
        unread = not outgoing and not row['read_at']
        add('internal', row['id'], 'user', 'outgoing' if outgoing else 'incoming', row['subject'], row['message'],
            row['sender_name'], row['recipient_name'], row['created_at'],
            unread=unread, status='sent' if outgoing else 'unread' if unread else 'read',
            reply_to={'id': 'u:' + row['sender_id'], 'name': row['sender_name']} if not outgoing else None)

    for row in con.execute("SELECT id,payload,created_at FROM ai_command_jobs WHERE user_id=? AND status!='draft'", (current['id'],)):
        payload = json.loads(row['payload'])
        for person in payload.get('recipients', []):
            status, channel = person.get('status'), person.get('channel')
            if status in ('skipped', 'pending') or channel not in ('user', 'email', 'sms'):
                continue
            # Successful internal deliveries are already represented by user_messages.
            if channel == 'user' and status == 'sent':
                continue
            add('dispatch', row['id'] + ':' + person['id'], channel, 'outgoing', payload.get('subject', ''),
                payload.get('message', ''), current['name'], person.get('name') or person.get('address'),
                person.get('sent_at') or payload.get('sent_at') or row['created_at'],
                address=person.get('address', '') if channel != 'user' else '', status=status or 'sending',
                error=person.get('reason', ''))

    for row in con.execute('''SELECT r.id,r.channel,r.user_id,r.name,r.email,r.phone,r.delivery_status,
        r.accepted_at,r.revoked,r.error,m.sender_id,m.sender_name,m.title,m.message,m.filename,m.created_at,m.expires
        FROM file_mail_recipients r JOIN file_mailings m ON m.id=r.mailing_id
        JOIN users s ON s.id=m.sender_id
        WHERE m.sender_id=? OR (r.channel='user' AND r.user_id=? AND s.active=1)''', (current['id'], current['id'])):
        outgoing = row['sender_id'] == current['id'] and not (row['channel'] == 'user' and row['user_id'] == current['id'])
        add('approval', row['id'], row['channel'], 'outgoing' if outgoing else 'incoming', row['title'], row['message'],
            row['sender_name'], row['name'] or row['email'] or row['phone'], row['created_at'],
            status=mailing.recipient_status(row, row['expires']), filename=row['filename'],
            address=row['phone'] if row['channel'] == 'sms' else row['email'], error=row['error'],
            reply_to={'id': 'u:' + row['sender_id'], 'name': row['sender_name']} if not outgoing and row['channel'] == 'user' else None)

    for row in con.execute('''SELECT r.id,r.title,r.notes,r.correspondent,r.address,r.reference,r.direction,
        r.status,r.record_date,i.remote_status FROM edelivery_records r
        LEFT JOIN edelivery_imports i ON i.record_id=r.id AND i.user_id=r.user_id WHERE r.user_id=?''', (current['id'],)):
        outgoing = row['direction'] == 'outgoing'
        add('edelivery', row['id'], 'edelivery', row['direction'], row['title'], row['notes'],
            current['name'] if outgoing else row['correspondent'], row['correspondent'] if outgoing else current['name'],
            row['record_date'], status=row['status'], remote_status=row['remote_status'],
            address=row['address'], reference=row['reference'])
    states = {row['message_id']: bool(row['unread']) for row in con.execute(
        'SELECT message_id,unread FROM message_center_read_state WHERE user_id=?', (current['id'],))}
    for item in rows:
        if item['direction'] == 'incoming' and item['source'] not in ('email', 'internal'):
            item['unread'] = states.get(item['id'], True)
    return rows


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError, TypeError, AttributeError):
        return 0


def install(app, db, user):
    @app.patch('/api/message-center/{identifier}/read-state')
    def set_read_state(identifier: str, body: ReadState, current=Depends(user)):
        with db() as con:
            con.begin_write()
            item = next((item for item in collect(con, current)
                         if item['id'] == identifier and item['direction'] == 'incoming'), None)
            if not item:
                raise HTTPException(404, 'Nie znaleziono wiadomości.')
            if item['source'] == 'email':
                raise HTTPException(400, 'Zmień status przez API poczty.')
            if item['source'] == 'internal':
                con.execute('UPDATE user_messages SET read_at=? WHERE id=? AND recipient_id=?',
                            (None if body.unread else datetime.now(timezone.utc).isoformat(), item['source_id'], current['id']))
            else:
                con.execute('''INSERT INTO message_center_read_state(user_id,message_id,unread) VALUES(?,?,?)
                    ON CONFLICT(user_id,message_id) DO UPDATE SET unread=excluded.unread''',
                    (current['id'], identifier, body.unread))
        return {'unread': body.unread}

    @app.get('/api/message-center')
    def listing(channel: Literal['all', 'email', 'user', 'sms', 'edelivery'] = 'all',
                direction: Literal['all', 'incoming', 'outgoing'] = 'all',
                search: str = Query(default='', max_length=200),
                offset: int = Query(default=0, ge=0), limit: int = Query(default=40, ge=1, le=100),
                current=Depends(user)):
        with db() as con:
            rows = collect(con, current)
        counts = dict(Counter(item['channel'] for item in rows))
        query = search.strip().casefold()
        filtered = [item for item in rows if (channel == 'all' or item['channel'] == channel)
                    and (direction == 'all' or item['direction'] == direction)
                    and (not query or query in ' '.join(str(item.get(key) or '') for key in
                         ('title', 'content', 'sender', 'recipient', 'address', 'filename', 'reference')).casefold())]
        filtered.sort(key=lambda item: (timestamp(item['created_at']), item['id']), reverse=True)
        return {'items': filtered[offset:offset + limit], 'total': len(filtered), 'counts': counts,
                'unread': sum(item['unread'] for item in rows), 'offset': offset, 'limit': limit}
