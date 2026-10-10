"""Recipient-specific approval links bound to an immutable copy of a sent file."""
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from email_validator import validate_email, EmailNotValidError
from backend import mailer, storage, sms

SCHEMA = '''
CREATE TABLE IF NOT EXISTS file_mailings(
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  sender_id TEXT NOT NULL REFERENCES users(id), sender_name TEXT NOT NULL,
  title TEXT NOT NULL, filename TEXT NOT NULL, version INTEGER NOT NULL, file_size INTEGER NOT NULL,
  file BYTEA, object_bucket TEXT, object_key TEXT, sha256 TEXT NOT NULL,
  message TEXT NOT NULL, created_at TEXT NOT NULL, expires DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS file_mail_recipients(
  id TEXT PRIMARY KEY, mailing_id TEXT NOT NULL REFERENCES file_mailings(id) ON DELETE CASCADE,
  email TEXT NOT NULL, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
  delivery_status TEXT NOT NULL DEFAULT 'sending', sent_at TEXT, accepted_at TEXT,
  revoked INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS file_mailing_document ON file_mailings(document_id,sender_id);
CREATE INDEX IF NOT EXISTS file_recipient_mailing ON file_mail_recipients(mailing_id);
'''

class Recipient(BaseModel):
    channel: Literal['email', 'user', 'sms'] = 'email'
    email: str = Field(default='', max_length=254)
    name: str = Field(default='', max_length=100)
    phone: str = Field(default='', max_length=30)
    user_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode='after')
    def valid_address(self):
        if self.channel == 'email':
            try:
                self.email = validate_email(self.email.strip(), check_deliverability=False, allow_smtputf8=False).ascii_email
            except EmailNotValidError:
                raise ValueError('Podaj poprawny adres e-mail.') from None
            self.phone = ''; self.user_id = None
        elif self.channel == 'sms':
            self.phone = sms.phone_number(self.phone)
            self.email = ''; self.user_id = None
        else:
            if not self.user_id or not self.user_id.strip(): raise ValueError('Wybierz użytkownika aplikacji.')
            self.email = ''; self.phone = ''
        return self

class SendInput(BaseModel):
    version: int = Field(strict=True, ge=1)
    recipients: list[Recipient] = Field(min_length=1, max_length=20)
    message: str = Field(default='', max_length=3000)
    days: int = Field(default=7, strict=True, ge=1, le=30)

    @field_validator('recipients')
    @classmethod
    def unique_recipients(cls, values):
        if len({(value.channel, (value.email or value.phone or value.user_id).lower()) for value in values}) != len(values):
            raise ValueError('Każdy odbiorca w danym kanale może wystąpić tylko raz.')
        return values

class AcceptInput(BaseModel):
    confirmed: bool = Field(strict=True)


def migrate(c):
    columns = c.columns('file_mail_recipients')
    for name, kind in [('channel', "TEXT NOT NULL DEFAULT 'email'"), ('phone', "TEXT NOT NULL DEFAULT ''"),
                       ('user_id', 'TEXT REFERENCES users(id)'), ('provider_id', "TEXT NOT NULL DEFAULT ''")]:
        if name not in columns: c.execute(f'ALTER TABLE file_mail_recipients ADD COLUMN {name} {kind}')
    if 'position' not in columns:
        c.execute('ALTER TABLE file_mail_recipients ADD COLUMN position INTEGER NOT NULL DEFAULT 0')
        c.execute('''WITH positions AS (
            SELECT id,row_number() OVER (PARTITION BY mailing_id ORDER BY id) AS pos FROM file_mail_recipients)
            UPDATE file_mail_recipients SET position=(SELECT pos FROM positions WHERE positions.id=file_mail_recipients.id)''')
    c.execute('CREATE INDEX IF NOT EXISTS file_recipient_user ON file_mail_recipients(user_id,channel)')

def recipient_status(row, expires):
    if row['accepted_at']:
        return 'accepted'
    if row['revoked']:
        return 'revoked'
    if row['delivery_status'] == 'failed':
        return 'failed'
    if expires <= datetime.now(timezone.utc).timestamp():
        return 'expired'
    if row['delivery_status'] == 'sending':
        return 'sending'
    return 'waiting'

def summary(c, doc_id, sender_id, version):
    rows = c.execute('''SELECT r.*,m.expires FROM file_mail_recipients r JOIN file_mailings m ON m.id=r.mailing_id
      WHERE m.document_id=? AND m.sender_id=? AND (? IS NULL OR m.version=?)''', (doc_id, sender_id, version, version)).fetchall()
    statuses = [recipient_status(row, row['expires']) for row in rows]
    return {status: statuses.count(status) for status in ('accepted', 'waiting', 'failed', 'expired', 'revoked', 'sending')}

def install(app, db, user, owned, file_response, file_bytes, now, digest):
    def history(c, doc_id, current):
        doc = owned(c, doc_id, current)
        if doc['user_id'] != current['id'] or (doc['uploaded_by'] or doc['user_id']) != current['id']:
            raise HTTPException(403, 'Historia wysyłek jest dostępna dla autora pliku.')
        result = []
        for row in c.execute('''SELECT id,title,filename,version,file_size,sha256,message,created_at,expires
          FROM file_mailings WHERE document_id=? AND sender_id=? ORDER BY created_at DESC''', (doc_id, current['id'])):
            item = dict(row)
            item['current_version'] = item['version'] == doc['version']
            item['recipients'] = []
            for recipient in c.execute('''SELECT id,email,name,channel,phone,user_id,delivery_status,sent_at,accepted_at,revoked,error
              FROM file_mail_recipients WHERE mailing_id=? ORDER BY position,id''', (row['id'],)):
                details = dict(recipient)
                details['status'] = recipient_status(recipient, row['expires'])
                item['recipients'].append(details)
            result.append(item)
        return result

    @app.get('/api/email-settings')
    def settings(current=Depends(user)):
        return mailer.settings_status()

    @app.get('/api/approval-settings')
    def channel_settings(current=Depends(user)):
        return {'email': mailer.settings_status(), 'sms': sms.settings_status(),
                'user': {'configured': True, 'message': ''}}

    @app.get('/api/documents/{doc_id}/emails')
    def sent_emails(doc_id: str, current=Depends(user)):
        with db() as c:
            return history(c, doc_id, current)

    @app.post('/api/documents/{doc_id}/emails', status_code=201)
    def send_email(doc_id: str, body: SendInput, current=Depends(user)):
        with db() as c:
            doc = owned(c, doc_id, current, 'send')
            if doc['version'] != body.version:
                raise HTTPException(409, 'Plik został zmieniony. Otwórz okno wysyłki ponownie.')
        channels = {person.channel for person in body.recipients}
        config = mailer.configuration() if 'email' in channels else None
        sms_config = sms.configuration() if 'sms' in channels else None
        data = file_bytes(doc)
        bucket, key = storage.put(data, current['id'])
        mailing_id = secrets.token_hex(16)
        timestamp = now()
        expires = datetime.now(timezone.utc).timestamp() + body.days * 86400
        recipients = [(secrets.token_hex(16), secrets.token_urlsafe(32), recipient.model_dump()) for recipient in body.recipients]
        try:
            with db() as c:
                c.begin_write()
                checked = owned(c, doc_id, current, 'send')
                if checked['version'] != body.version:
                    raise HTTPException(409, 'Plik został zmieniony. Otwórz okno wysyłki ponownie.')
                for _, _, recipient in recipients:
                    if recipient['channel'] == 'user':
                        target = c.execute('SELECT id,name FROM users WHERE id=? AND active=1', (recipient['user_id'],)).fetchone()
                        if not target: raise HTTPException(422, 'Wybrany użytkownik nie istnieje lub jest nieaktywny.')
                        recipient['name'] = target['name']
                c.execute('''INSERT INTO file_mailings(id,document_id,sender_id,sender_name,title,filename,version,file_size,
                  file,object_bucket,object_key,sha256,message,created_at,expires) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                          (mailing_id, doc_id, current['id'], current['name'], doc['title'], doc['filename'], doc['version'],
                           len(data), None if key else data, bucket, key, hashlib.sha256(data).hexdigest(), body.message.strip(), timestamp, expires))
                for position, (recipient_id, token, recipient) in enumerate(recipients, 1):
                    c.execute('''INSERT INTO file_mail_recipients(id,mailing_id,email,name,token_hash,channel,phone,user_id,
                        delivery_status,sent_at,position) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                              (recipient_id, mailing_id, recipient['email'], recipient['name'].strip(), digest(token),
                               recipient['channel'], recipient['phone'], recipient['user_id'],
                               'sent' if recipient['channel'] == 'user' else 'sending', timestamp if recipient['channel'] == 'user' else None, position))
        except Exception:
            storage.cleanup(bucket, key)
            raise
        expires_at = datetime.fromtimestamp(expires, timezone.utc).strftime('%Y-%m-%d %H:%M')
        for recipient_id, token, recipient in recipients:
            if recipient['channel'] == 'user': continue
            provider_id = ''
            try:
                if recipient['channel'] == 'email':
                    mailer.send_file(config, recipient, current['name'], doc['filename'], data, doc['version'],
                                     config['public_url'] + '/accept/' + token, body.message.strip(), expires_at)
                else:
                    provider_id = sms.send_link(sms_config, recipient['phone'], doc['filename'], doc['version'],
                                                sms_config['public_url'] + '/accept/' + token, body.days)
                delivery, sent_at, error = 'sent', now(), ''
            except HTTPException as exc:
                delivery, sent_at, error = 'failed', None, exc.detail
            with db() as c:
                c.execute('UPDATE file_mail_recipients SET delivery_status=?,sent_at=?,error=?,provider_id=? WHERE id=?',
                          (delivery, sent_at, error, provider_id, recipient_id))
        with db() as c:
            return {'mailing_id': mailing_id, 'history': history(c, doc_id, current)}

    @app.post('/api/documents/{doc_id}/emails/{recipient_id}/revoke', status_code=204)
    def revoke(doc_id: str, recipient_id: str, current=Depends(user)):
        with db() as c:
            c.begin_write()
            history(c, doc_id, current)
            row = c.execute('''SELECT r.* FROM file_mail_recipients r JOIN file_mailings m ON m.id=r.mailing_id
              WHERE r.id=? AND m.document_id=? AND m.sender_id=?''', (recipient_id, doc_id, current['id'])).fetchone()
            if not row:
                raise HTTPException(404, 'Nie znaleziono odbiorcy.')
            if row['accepted_at']:
                raise HTTPException(409, 'Akceptacja została już zapisana; nie można jej cofnąć.')
            c.execute('UPDATE file_mail_recipients SET revoked=1 WHERE id=?', (recipient_id,))

    def linked(c, token):
        row = c.execute('''SELECT r.id AS recipient_id,r.email,r.name,r.channel,r.phone,r.user_id,r.delivery_status,r.accepted_at,r.revoked,
          m.* FROM file_mail_recipients r JOIN file_mailings m ON m.id=r.mailing_id
          JOIN users u ON u.id=m.sender_id WHERE r.token_hash=? AND u.active=1''', (digest(token),)).fetchone()
        if not row:
            raise HTTPException(404, 'Link akceptacji nie istnieje.')
        if row['channel'] == 'user': raise HTTPException(404, 'Użyj skrzynki akceptacji po zalogowaniu.')
        if row['revoked'] or row['expires'] <= datetime.now(timezone.utc).timestamp():
            raise HTTPException(410, 'Link akceptacji wygasł lub został cofnięty.')
        if row['delivery_status'] == 'sending':
            raise HTTPException(409, 'Wiadomość jest jeszcze wysyłana. Spróbuj ponownie za chwilę.')
        if row['delivery_status'] != 'sent':
            raise HTTPException(410, 'Wysyłka tej wiadomości nie została potwierdzona. Poproś nadawcę o nowy link.')
        return row

    def public_details(row):
        return {key: row[key] for key in ('title', 'filename', 'version', 'file_size', 'sender_name', 'email', 'name', 'channel', 'phone', 'message', 'created_at', 'expires', 'accepted_at')}

    def internal(c, identifier, current):
        row = c.execute('''SELECT r.id AS recipient_id,r.email,r.name,r.channel,r.phone,r.delivery_status,
          r.accepted_at,r.revoked,m.* FROM file_mail_recipients r JOIN file_mailings m ON m.id=r.mailing_id
          JOIN users u ON u.id=m.sender_id WHERE r.id=? AND r.channel='user' AND r.user_id=? AND u.active=1''',
                        (identifier, current['id'])).fetchone()
        if not row: raise HTTPException(404, 'Nie znaleziono prośby o akceptację.')
        if recipient_status(row, row['expires']) not in ('waiting', 'accepted'):
            raise HTTPException(410, 'Prośba o akceptację wygasła lub została cofnięta.')
        if row['expires'] <= datetime.now(timezone.utc).timestamp() or row['revoked']:
            raise HTTPException(410, 'Prośba o akceptację wygasła lub została cofnięta.')
        return row

    @app.get('/api/approval-inbox')
    def inbox(current=Depends(user)):
        with db() as c:
            rows = c.execute('''SELECT r.id AS recipient_id,r.email,r.name,r.channel,r.phone,r.delivery_status,
              r.accepted_at,r.revoked,m.title,m.filename,m.version,m.file_size,m.sender_name,m.message,m.created_at,m.expires
              FROM file_mail_recipients r JOIN file_mailings m ON m.id=r.mailing_id
              JOIN users u ON u.id=m.sender_id WHERE r.channel='user' AND r.user_id=? AND u.active=1
              ORDER BY m.created_at DESC,r.id''', (current['id'],)).fetchall()
            return [{**public_details(row), 'id': row['recipient_id'], 'status': recipient_status(row, row['expires'])} for row in rows]

    @app.get('/api/approval-inbox/{identifier}/file')
    def internal_download(identifier: str, current=Depends(user)):
        with db() as c: return file_response(internal(c, identifier, current))

    @app.post('/api/approval-inbox/{identifier}/accept')
    def internal_accept(identifier: str, body: AcceptInput, current=Depends(user)):
        if not body.confirmed: raise HTTPException(422, 'Potwierdź akceptację pliku.')
        with db() as c:
            c.begin_write()
            row = internal(c, identifier, current)
            if not row['accepted_at']:
                c.execute('UPDATE file_mail_recipients SET accepted_at=? WHERE id=?', (now(), identifier))
            return {**public_details(internal(c, identifier, current)), 'id': identifier, 'status': 'accepted'}

    @app.get('/api/approvals/{token}')
    def approval(token: str):
        with db() as c:
            return public_details(linked(c, token))

    @app.get('/api/approvals/{token}/file')
    def download(token: str):
        with db() as c:
            return file_response(linked(c, token))

    @app.post('/api/approvals/{token}/accept')
    def accept(token: str, body: AcceptInput):
        if not body.confirmed:
            raise HTTPException(422, 'Zaznacz potwierdzenie akceptacji pliku.')
        with db() as c:
            c.begin_write()
            row = linked(c, token)
            if not row['accepted_at']:
                c.execute('UPDATE file_mail_recipients SET accepted_at=? WHERE id=?', (now(), row['recipient_id']))
            return public_details(linked(c, token))
