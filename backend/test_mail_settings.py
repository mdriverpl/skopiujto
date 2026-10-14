import json
import smtplib
import pytest
from backend import mail_settings, mailer
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch, tmp_path):
    monkeypatch.delenv('EDOCUMENTS_MAIL_SETTINGS_KEY', raising=False)
    monkeypatch.setattr(mail_settings, 'KEY_FILE', tmp_path / 'mail.key')


def account():
    return {'email': 'jan@example.com', 'sender_name': 'Jan Kowalski', 'version': 0,
        'smtp': {'enabled': True, 'host': 'smtp.example.com', 'port': 465, 'security': 'ssl',
                 'username': 'jan@example.com', 'password': 'smtp-private-password'},
        'imap': {'enabled': True, 'host': 'imap.example.com', 'port': 993, 'security': 'ssl',
                 'username': 'jan@example.com', 'password': 'imap-private-password'}}


def test_save_encrypts_passwords_and_only_returns_presence_flags(app_client):
    main, client = app_client
    response = client.put('/api/client-mail/settings', json=account())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['account']['version'] == 1 and data['smtp']['source'] == 'personal'
    assert data['account']['smtp']['has_password'] is True
    assert 'private-password' not in response.text and '"password"' not in response.text
    with main.db() as con:
        row = con.execute('SELECT * FROM client_mail_settings').fetchone()
        assert 'private-password' not in row['config'] and 'private-password' not in row['secrets']
        assert mail_settings.credentials(row)['smtp'] == 'smtp-private-password'
    assert client.get('/api/client-mail/settings').json() == data


def test_empty_password_preserves_secret_conflict_and_clear(app_client):
    main, client = app_client
    saved = client.put('/api/client-mail/settings', json=account()).json()['account']
    saved['sender_name'] = 'Nowa nazwa'
    saved['smtp']['password'] = ''; saved['imap']['password'] = None
    response = client.put('/api/client-mail/settings', json=saved)
    assert response.status_code == 200 and response.json()['account']['version'] == 2
    assert client.put('/api/client-mail/settings', json=saved).status_code == 409
    with main.db() as con:
        row = con.execute('SELECT * FROM client_mail_settings').fetchone()
        assert mail_settings.credentials(row)['imap'] == 'imap-private-password'
    saved = response.json()['account']
    saved['imap']['enabled'] = False; saved['imap']['clear_password'] = True
    assert client.put('/api/client-mail/settings', json=saved).json()['account']['imap']['has_password'] is False


def test_personal_settings_are_isolated_and_sending_uses_own_smtp(app_client, monkeypatch):
    _, client = app_client
    client.put('/api/client-mail/settings', json=account())
    sent = []
    monkeypatch.setattr(mailer, 'send_message', lambda *args: sent.append(args))
    draft = client.post('/api/client-mail/drafts', json={'recipient': 'anna@example.com', 'subject': 'Test', 'content': 'Moja treść'}).json()
    response = client.post('/api/client-mail/' + draft['id'] + '/send', json={'version': 1})
    assert response.status_code == 200, response.text
    assert response.json()['sender_email'] == 'jan@example.com'
    assert sent[0][0]['host'] == 'smtp.example.com' and sent[0][0]['password'] == 'smtp-private-password'
    assert sent[0][2] == 'Jan Kowalski'
    create_reader(client); login(client, READER)
    assert client.get('/api/client-mail/settings').json()['account']['version'] == 0
    assert client.post('/api/client-mail/settings/test/smtp').status_code == 422
    reader = account(); reader['email'] = 'reader@example.com'
    assert client.put('/api/client-mail/settings', json=reader).status_code == 200
    login(client, ADMIN)
    assert client.get('/api/client-mail/settings').json()['account']['email'] == 'jan@example.com'
    client.post('/api/logout')
    assert client.get('/api/client-mail/settings').status_code == 401
    assert client.put('/api/client-mail/settings', json=account()).status_code == 401
    assert client.post('/api/client-mail/settings/test/smtp').status_code == 401


def test_settings_validation_and_disabled_smtp(app_client, monkeypatch):
    _, client = app_client
    for field, value in [('host', 'https://smtp.example.com'), ('port', 0), ('security', 'none')]:
        body = account(); body['smtp'][field] = value
        assert client.put('/api/client-mail/settings', json=body).status_code == 422
    body = account(); body['smtp']['password'] = ''
    assert client.put('/api/client-mail/settings', json=body).status_code == 422
    body = account(); body['smtp']['enabled'] = False
    assert client.put('/api/client-mail/settings', json=body).status_code == 200
    def unexpected(*args): pytest.fail('Disabled personal SMTP must not fall back to server SMTP')
    monkeypatch.setattr(mailer, 'send_message', unexpected)
    draft = client.post('/api/client-mail/drafts', json={'recipient': 'anna@example.com', 'subject': 'Test', 'content': 'Treść'}).json()
    assert client.post('/api/client-mail/' + draft['id'] + '/send', json={'version': 1}).status_code == 503


def test_connection_checks_login_without_sending_and_masks_provider_error(app_client, monkeypatch):
    _, client = app_client
    client.put('/api/client-mail/settings', json=account())
    calls = []
    class SMTP:
        def __init__(self, *args, **kwargs): calls.append('connect')
        def login(self, username, password): calls.append(('login', username, password))
        def noop(self): calls.append('noop'); return 250, b'OK'
        def quit(self): calls.append('quit')
    monkeypatch.setattr(mail_settings.smtplib, 'SMTP_SSL', SMTP)
    assert client.post('/api/client-mail/settings/test/smtp').status_code == 200
    assert calls == ['connect', ('login', 'jan@example.com', 'smtp-private-password'), 'noop', 'quit']
    def failing(*args, **kwargs): raise smtplib.SMTPAuthenticationError(535, b'private-password in error')
    monkeypatch.setattr(mail_settings.smtplib, 'SMTP_SSL', failing)
    response = client.post('/api/client-mail/settings/test/smtp')
    assert response.status_code == 502 and 'private-password' not in response.text
    class IMAP:
        def __init__(self, *args, **kwargs): pass
        def login(self, username, password): assert password == 'imap-private-password'
        def noop(self): return 'OK', []
        def logout(self): pass
    monkeypatch.setattr(mail_settings.imaplib, 'IMAP4_SSL', IMAP)
    assert client.post('/api/client-mail/settings/test/imap').status_code == 200
