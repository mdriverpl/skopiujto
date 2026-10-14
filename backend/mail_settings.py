"""Personal mail configuration; passwords are encrypted and never returned."""
import imaplib
import json
import os
import smtplib
import ssl
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken
from email_validator import validate_email, EmailNotValidError
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from backend import ai, mailer

SCHEMA = '''
CREATE TABLE IF NOT EXISTS client_mail_settings(
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 config TEXT NOT NULL, secrets TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
'''


class Transport(BaseModel):
    enabled: bool = False
    host: str = Field(default='', max_length=253)
    port: int = Field(ge=1, le=65535)
    security: Literal['ssl', 'starttls'] = 'ssl'
    username: str = Field(default='', max_length=254)
    password: str | None = Field(default=None, max_length=1000)
    clear_password: bool = False

    @field_validator('host', 'username')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Usuń niedozwolone znaki z danych serwera.')
        return value

    @field_validator('host')
    @classmethod
    def host_only(cls, value):
        if value and (any(c.isspace() for c in value) or any(c in value for c in '/:@?#\\')):
            raise ValueError('Podaj nazwę serwera bez protokołu i portu, np. smtp.firma.pl.')
        return value

    @model_validator(mode='after')
    def complete(self):
        if self.enabled and not self.host:
            raise ValueError('Podaj adres włączonego serwera.')
        return self


class Account(BaseModel):
    email: str = Field(default='', max_length=254)
    sender_name: str = Field(default='', max_length=150)
    smtp: Transport = Field(default_factory=lambda: Transport(port=465))
    imap: Transport = Field(default_factory=lambda: Transport(port=993))
    version: int = Field(default=0, ge=0)

    @field_validator('sender_name')
    @classmethod
    def name(cls, value):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Nazwa nadawcy zawiera niedozwolone znaki.')
        return value.strip()

    @field_validator('email')
    @classmethod
    def address(cls, value):
        if not value.strip(): return ''
        try: return validate_email(value.strip(), check_deliverability=False, allow_smtputf8=False).ascii_email
        except EmailNotValidError: raise ValueError('Podaj poprawny adres e-mail.') from None

    @model_validator(mode='after')
    def complete(self):
        if (self.smtp.enabled or self.imap.enabled) and not self.email:
            raise ValueError('Podaj adres e-mail konta.')
        if self.imap.enabled and not self.imap.username:
            raise ValueError('Podaj login IMAP.')
        return self


def cipher():
    key = os.getenv('EDOCUMENTS_MAIL_SETTINGS_KEY', '').strip()
    if not key:
        raise HTTPException(503, 'Brak klucza szyfrowania ustawień poczty na serwerze. Ustaw EDOCUMENTS_MAIL_SETTINGS_KEY w .env i uruchom ponownie backend.') from None
    try: return Fernet(key)
    except (ValueError, TypeError):
        raise HTTPException(503, 'Niepoprawny klucz szyfrowania ustawień poczty na serwerze.') from None


def credentials(row):
    try: return json.loads(cipher().decrypt(row['secrets'].encode()))
    except (InvalidToken, ValueError):
        raise HTTPException(503, 'Nie można odczytać haseł poczty. Sprawdź klucz szyfrowania na serwerze.') from None


def public_settings(con, current):
    row = con.execute('SELECT * FROM client_mail_settings WHERE user_id=?', (current['id'],)).fetchone()
    if row:
        account = json.loads(row['config'])
        account['version'] = row['version']
        status = {'configured': account['smtp']['enabled'], 'message': '' if account['smtp']['enabled'] else 'Włącz i uzupełnij SMTP w ustawieniach poczty.', 'source': 'personal'}
    else:
        account = Account(email=current.get('email') or '', sender_name=current['name']).model_dump()
        for name in ('smtp', 'imap'):
            account[name].pop('password'); account[name].pop('clear_password'); account[name]['has_password'] = False
        status = {**mailer.settings_status(), 'source': 'server'}
    return {'account': account, 'smtp': status, 'ai': ai.configuration(), 'import_only': not account['imap']['enabled']}


def smtp_config(con, current):
    row = con.execute('SELECT * FROM client_mail_settings WHERE user_id=?', (current['id'],)).fetchone()
    if not row: return mailer.configuration(), current['name']
    account = json.loads(row['config'])
    transport = account['smtp']
    if not transport['enabled']:
        raise HTTPException(503, 'Włącz SMTP w ustawieniach poczty.')
    return {**transport, 'sender': account['email'], 'password': credentials(row)['smtp']}, account['sender_name'] or current['name']


def test_connection(transport, config):
    connection = None
    try:
        if transport == 'smtp':
            if config['security'] == 'ssl':
                connection = smtplib.SMTP_SSL(config['host'], config['port'], timeout=15, context=ssl.create_default_context())
            else:
                connection = smtplib.SMTP(config['host'], config['port'], timeout=15)
                connection.starttls(context=ssl.create_default_context())
            if config['username']: connection.login(config['username'], config['password'])
            code, _ = connection.noop()
            if not 200 <= code < 300: raise smtplib.SMTPException('NOOP rejected')
        else:
            if config['security'] == 'ssl':
                connection = imaplib.IMAP4_SSL(config['host'], config['port'], ssl_context=ssl.create_default_context(), timeout=15)
            else:
                connection = imaplib.IMAP4(config['host'], config['port'], timeout=15)
                connection.starttls(ssl_context=ssl.create_default_context())
            connection.login(config['username'], config['password'])
            status, _ = connection.noop()
            if status != 'OK': raise imaplib.IMAP4.error('NOOP rejected')
    except (OSError, smtplib.SMTPException, imaplib.IMAP4.error):
        raise HTTPException(502, f'Połączenie {transport.upper()} nie powiodło się. Sprawdź serwer, port, zabezpieczenia, login i hasło.') from None
    finally:
        if connection:
            try:
                if transport == 'smtp': connection.quit()
                else: connection.logout()
            except (OSError, smtplib.SMTPException, imaplib.IMAP4.error): pass
    return {'message': f'Połączenie {transport.upper()} działa poprawnie. Nie wysłano ani nie pobrano wiadomości.'}


def install(app, db, user):
    @app.get('/api/client-mail/settings')
    def settings(current=Depends(user)):
        with db() as con: return public_settings(con, current)

    @app.put('/api/client-mail/settings')
    def save(body: Account, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = con.execute('SELECT * FROM client_mail_settings WHERE user_id=?', (current['id'],)).fetchone()
            if body.version != (row['version'] if row else 0):
                raise HTTPException(409, 'Ustawienia zostały zmienione. Otwórz je ponownie przed zapisem.')
            secret = credentials(row) if row else {'smtp': '', 'imap': ''}
            data = body.model_dump(exclude={'version'})
            for name in ('smtp', 'imap'):
                transport = data[name]
                password = transport.pop('password')
                clear = transport.pop('clear_password')
                if clear: secret[name] = ''
                elif password: secret[name] = password
                if transport['enabled'] and transport['username'] and not secret[name]:
                    raise HTTPException(422, f'Podaj hasło {name.upper()} lub hasło aplikacji.')
                transport['has_password'] = bool(secret[name])
            encrypted = cipher().encrypt(json.dumps(secret).encode()).decode()
            con.execute('''INSERT INTO client_mail_settings(user_id,config,secrets,version) VALUES(?,?,?,1)
                ON CONFLICT(user_id) DO UPDATE SET config=excluded.config,secrets=excluded.secrets,version=client_mail_settings.version+1''',
                (current['id'], json.dumps(data), encrypted))
            return public_settings(con, current)

    @app.post('/api/client-mail/settings/test/{transport}')
    def test(transport: Literal['smtp', 'imap'], current=Depends(user)):
        with db() as con:
            row = con.execute('SELECT * FROM client_mail_settings WHERE user_id=?', (current['id'],)).fetchone()
            if not row: raise HTTPException(422, 'Najpierw zapisz ustawienia poczty.')
            config = json.loads(row['config'])[transport]
            if not config['enabled']: raise HTTPException(422, f'Najpierw włącz {transport.upper()} i zapisz ustawienia.')
            config['password'] = credentials(row)[transport]
        return test_connection(transport, config)


def imap_config(con, current):
    row = con.execute('SELECT * FROM client_mail_settings WHERE user_id=?', (current['id'],)).fetchone()
    if not row:
        raise HTTPException(422, 'Najpierw zapisz ustawienia poczty IMAP.')
    config = json.loads(row['config'])['imap']
    if not config['enabled']:
        raise HTTPException(422, 'Włącz IMAP w ustawieniach poczty i zapisz zmiany.')
    return {**config, 'password': credentials(row)['imap']}
