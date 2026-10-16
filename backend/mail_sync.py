"""Explicit, read-only IMAP receiving with owner/account/UID deduplication."""
import hashlib
import imaplib
import re
import secrets
import ssl
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from fastapi import HTTPException
from backend import mail_rules, mail_attachments

SCHEMA = '''
CREATE TABLE IF NOT EXISTS client_mail_imap(
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 account TEXT NOT NULL, uid_validity TEXT NOT NULL, uid TEXT NOT NULL,
 mail_id TEXT NOT NULL REFERENCES client_mail(id) ON DELETE CASCADE,
 PRIMARY KEY(user_id,account,uid_validity,uid));
'''
MAX_BYTES = 10 * 1024 * 1024
BATCH_SIZE = 100
ALLOWED_HOURS = (24, 48, 168, 720)


def utc_now():
    return datetime.now(timezone.utc)


def internal_time(header):
    match = re.search(rb'INTERNALDATE "([^"]+)"', header)
    if not match: raise imaplib.IMAP4.error('Missing internal date')
    try:
        return parsedate_to_datetime(match[1].decode('ascii').replace('-', ' ', 2)).astimezone(timezone.utc)
    except (ValueError, TypeError, UnicodeError):
        raise imaplib.IMAP4.error('Invalid internal date') from None


def checked(result):
    status, data = result
    if status != 'OK':
        raise imaplib.IMAP4.error('IMAP command rejected')
    return data


def receive(db, current, config, parse_message, now, hours=24):
    if hours not in ALLOWED_HOURS: raise HTTPException(422, 'Wybierz zakres: 24 h, 48 h, 7 dni lub 30 dni.')
    cutoff = utc_now() - timedelta(hours=hours)
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
        # SINCE has day precision and ignores timezones. Search one extra day,
        # then enforce the exact rolling window using server INTERNALDATE.
        day = (cutoff - timedelta(days=1)).date()
        month = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')[day.month - 1]
        data = checked(connection.uid('search', None, 'SINCE', f'{day.day:02d}-{month}-{day.year}'))
        uids = (data[0] or b'').split()
        if any(not uid.isdigit() for uid in uids):
            raise imaplib.IMAP4.error('Invalid UID')
        with db() as con:
            known = {row['uid'] for row in con.execute(
                'SELECT uid FROM client_mail_imap WHERE user_id=? AND account=? AND uid_validity=?',
                (current['id'], account, uid_validity))}
        pending = sorted({uid for uid in uids if uid.decode('ascii') not in known}, key=int)
        eligible = []
        for offset in range(0, len(pending), 200):
            batch = pending[offset:offset + 200]
            metadata = checked(connection.uid('fetch', b','.join(batch), '(UID RFC822.SIZE FLAGS INTERNALDATE)'))
            for item in metadata:
                header = item[0] if isinstance(item, tuple) else item
                if not isinstance(header, bytes): continue
                match = re.search(rb'\bUID\s+(\d+)', header)
                if not match or match[1] not in batch: continue
                received = internal_time(header)
                if received >= cutoff: eligible.append((match[1], header, received))
        eligible.sort(key=lambda item: (item[2], int(item[0])), reverse=True)
        for uid, header, received in eligible[:BATCH_SIZE]:
            size = re.search(rb'RFC822.SIZE\s+(\d+)', header)
            if not size:
                raise imaplib.IMAP4.error('Missing message size')
            if int(size[1]) > MAX_BYTES:
                skipped += 1
                continue
            try:
                parsed = mail_attachments.read_message(connection, uid, parse_message)
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
                    int(b'\\Seen' not in header), received.isoformat()))
                mail_rules.mark_incoming(con, identifier, current['id'])
                for name, size, section in parsed['remote_attachments']:
                    con.execute('INSERT INTO client_mail_attachments(id,mail_id,name,size,remote_section) VALUES(?,?,?,?,?)',
                                (secrets.token_hex(16), identifier, name, size, section))
                con.execute('INSERT INTO client_mail_imap(user_id,account,uid_validity,uid,mail_id) VALUES(?,?,?,?,?)',
                            (current['id'], account, uid_validity, uid.decode(), identifier))
            imported += 1
        return {'imported': imported, 'skipped': skipped, 'remaining': max(0, len(eligible) - BATCH_SIZE)}
    except (OSError, imaplib.IMAP4.error):
        raise HTTPException(502, 'Nie udało się odebrać poczty IMAP. Sprawdź ustawienia i połączenie. Pobrane wcześniej wiadomości zachowano; ponów odświeżenie.') from None
    finally:
        if connection:
            try: connection.logout()
            except (OSError, imaplib.IMAP4.error): pass
