"""Explicit, read-only IMAP receiving with owner/account/UID deduplication."""
import hashlib
import imaplib
import re
import secrets
import ssl
from fastapi import HTTPException
from backend import mail_rules

SCHEMA = '''
CREATE TABLE IF NOT EXISTS client_mail_imap(
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 account TEXT NOT NULL, uid_validity TEXT NOT NULL, uid TEXT NOT NULL,
 mail_id TEXT NOT NULL REFERENCES client_mail(id) ON DELETE CASCADE,
 PRIMARY KEY(user_id,account,uid_validity,uid));
'''
MAX_BYTES = 10 * 1024 * 1024
BATCH_SIZE = 100


def checked(result):
    status, data = result
    if status != 'OK':
        raise imaplib.IMAP4.error('IMAP command rejected')
    return data


def receive(db, current, config, parse_message, now):
    connection = None
    imported = skipped = 0
    account = hashlib.sha256(repr((config['host'].lower(), config['port'], config['username'], 'INBOX')).encode()).hexdigest()
    try:
        if config['security'] == 'ssl':
            connection = imaplib.IMAP4_SSL(config['host'], config['port'], ssl_context=ssl.create_default_context(), timeout=15)
        else:
            connection = imaplib.IMAP4(config['host'], config['port'], timeout=15)
            checked(connection.starttls(ssl_context=ssl.create_default_context()))
        checked(connection.login(config['username'], config['password']))
        checked(connection.select('INBOX', readonly=True))
        _, validity = connection.response('UIDVALIDITY')
        if not validity or not validity[0] or not validity[0].isdigit():
            raise imaplib.IMAP4.error('Missing UIDVALIDITY')
        uid_validity = validity[0].decode('ascii')
        data = checked(connection.uid('search', None, 'ALL'))
        uids = (data[0] or b'').split()
        if any(not uid.isdigit() for uid in uids):
            raise imaplib.IMAP4.error('Invalid UID')
        with db() as con:
            known = {row['uid'] for row in con.execute(
                'SELECT uid FROM client_mail_imap WHERE user_id=? AND account=? AND uid_validity=?',
                (current['id'], account, uid_validity))}
        pending = [uid for uid in uids if uid.decode('ascii') not in known]
        for uid in pending[-BATCH_SIZE:]:
            metadata = checked(connection.uid('fetch', uid, '(RFC822.SIZE FLAGS)'))
            header = b' '.join(item for item in metadata if isinstance(item, bytes))
            size = re.search(rb'RFC822.SIZE\s+(\d+)', header)
            if not size:
                raise imaplib.IMAP4.error('Missing message size')
            if int(size[1]) > MAX_BYTES:
                skipped += 1
                continue
            data = checked(connection.uid('fetch', uid, '(BODY.PEEK[])'))
            raw = next((item[1] for item in data if isinstance(item, tuple) and isinstance(item[1], bytes)), None)
            if raw is None:
                raise imaplib.IMAP4.error('Missing message body')
            try:
                if len(raw) > MAX_BYTES: raise ValueError('Message too large')
                parsed = parse_message(raw)
            except (ValueError, LookupError, UnicodeError):
                skipped += 1
                continue
            with db() as con:
                con.begin_write()
                # Another request may have imported this UID while fetching.
                if con.execute('SELECT 1 FROM client_mail_imap WHERE user_id=? AND account=? AND uid_validity=? AND uid=?',
                               (current['id'], account, uid_validity, uid.decode())).fetchone():
                    continue
                identifier = secrets.token_hex(16)
                incoming_folder = mail_rules.apply_incoming(con, current['id'], parsed['sender_email'], parsed['subject'], parsed['content'])
                con.execute('''INSERT INTO client_mail(id,user_id,sender_name,sender_email,recipient,subject,content,folder,unread,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)''', (identifier, current['id'], parsed['sender_name'],
                    parsed['sender_email'], parsed['recipient'], parsed['subject'], parsed['content'], incoming_folder,
                    int(b'\\Seen' not in header), parsed['timestamp'] or now()))
                mail_rules.mark_incoming(con, identifier, current['id'])
                for name, payload in parsed['attachments']:
                    con.execute('INSERT INTO client_mail_attachments(id,mail_id,name,size,data) VALUES(?,?,?,?,?)',
                                (secrets.token_hex(16), identifier, name, len(payload), payload))
                con.execute('INSERT INTO client_mail_imap(user_id,account,uid_validity,uid,mail_id) VALUES(?,?,?,?,?)',
                            (current['id'], account, uid_validity, uid.decode(), identifier))
            imported += 1
        return {'imported': imported, 'skipped': skipped, 'remaining': max(0, len(pending) - BATCH_SIZE)}
    except (OSError, imaplib.IMAP4.error):
        raise HTTPException(502, 'Nie udało się odebrać poczty IMAP. Sprawdź ustawienia i połączenie. Pobrane wcześniej wiadomości zachowano; ponów odświeżenie.') from None
    finally:
        if connection:
            try: connection.logout()
            except (OSError, imaplib.IMAP4.error): pass
