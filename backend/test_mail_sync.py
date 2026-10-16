import imaplib
import pytest
from email import policy
from email.parser import BytesParser
from datetime import datetime, timedelta, timezone
from backend import mail_sync, mail_settings
from backend.test_client_mail import eml
from backend.test_storage import app_client
from backend.test_mail_settings import account, encryption_key
from backend.test_access import READER, create_reader, login


class FakeIMAP:
    error = imaplib.IMAP4.error
    validity = b'123'
    fail = False
    calls = []
    clock = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    uids = [b'1', b'2']
    dates = {}
    def __init__(self, *args, **kwargs): pass
    def login(self, *args): return 'OK', []
    def starttls(self, **kwargs): return 'OK', []
    def select(self, folder, readonly=False):
        assert folder == 'INBOX' and readonly
        return 'OK', [b'2']
    def response(self, name): return name, [self.validity]
    def uid(self, command, *args):
        self.calls.append((command, args))
        if self.fail: raise imaplib.IMAP4.error('private server error')
        if command == 'search':
            assert len(args) == 3 and args[:2] == (None, 'SINCE')
            return 'OK', [b' '.join(self.uids)]
        if args[1] == '(UID RFC822.SIZE FLAGS INTERNALDATE)':
            return 'OK', [b'1 (UID ' + uid + b' RFC822.SIZE 300 FLAGS (' + (b'\\Seen' if uid == b'2' else b'') + b') INTERNALDATE "' +
                          self.dates.get(uid, self.clock - timedelta(hours=1)).strftime('%d-%b-%Y %H:%M:%S %z').encode() + b'")'
                          for uid in args[0].split(b',')]
        message = BytesParser(policy=policy.default).parsebytes(eml())
        if args[1] == '(BODYSTRUCTURE)':
            return 'OK', [b'1 (BODYSTRUCTURE (("TEXT" "PLAIN" NIL NIL NIL "8BIT" 80 1)("APPLICATION" "PDF" NIL NIL NIL "BASE64" 16) "MIXED"))']
        section = args[1].split('[')[1].split(']')[0]
        if section == 'HEADER':
            payload = message.as_bytes().split(b'\n\n', 1)[0] + b'\n\n'
        else:
            number = int(section.split('.')[0])
            part = list(message.iter_parts())[number - 1]
            headers, body = part.as_bytes().split(b'\n\n', 1)
            payload = headers + b'\n\n' if section.endswith('.MIME') else body
        return 'OK', [(b'1 (BODY[' + section.encode() + b'] {300}', payload), b')']
    def logout(self): return 'BYE', []


@pytest.fixture
def imap(monkeypatch):
    FakeIMAP.calls = []; FakeIMAP.validity = b'123'; FakeIMAP.fail = False
    FakeIMAP.uids = [b'1', b'2']; FakeIMAP.dates = {}
    monkeypatch.setattr(mail_sync, 'utc_now', lambda: FakeIMAP.clock)
    monkeypatch.setattr(mail_sync.imaplib, 'IMAP4_SSL', FakeIMAP)
    monkeypatch.setattr(mail_sync.imaplib, 'IMAP4', FakeIMAP)
    return FakeIMAP


def test_receive_readonly_deduplicates_and_retains_local_changes(app_client, imap):
    _, client = app_client
    assert client.put('/api/client-mail/settings', json=account()).status_code == 200
    result = client.post('/api/client-mail/sync')
    assert result.status_code == 200, result.text
    assert result.json() == {'imported': 2, 'skipped': 0, 'remaining': 0}
    messages = client.get('/api/client-mail').json()
    assert sorted(m['unread'] for m in messages) == [0, 1]
    assert all(m['attachments'][0]['name'] == 'Oferta.pdf' for m in messages)
    assert client.patch('/api/client-mail/' + messages[0]['id'], json={'version': 1, 'folder': 'archive'}).status_code == 200
    before = len(imap.calls)
    assert client.post('/api/client-mail/sync').json()['imported'] == 0
    assert all(cmd == 'search' for cmd, _ in imap.calls[before:])
    assert len(client.get('/api/client-mail').json()) == 2
    assert any(m['folder'] == 'archive' for m in client.get('/api/client-mail').json())
    imap.validity = b'124'
    assert client.post('/api/client-mail/sync').json()['imported'] == 2


def test_receive_requires_personal_imap_and_authentication(app_client, imap):
    _, client = app_client
    assert client.post('/api/client-mail/sync').status_code == 422
    body = account(); body['imap']['security'] = 'starttls'
    assert client.put('/api/client-mail/settings', json=body).status_code == 200
    assert client.post('/api/client-mail/sync').json()['imported'] == 2
    create_reader(client); login(client, READER)
    assert client.post('/api/client-mail/sync').status_code == 422
    assert client.get('/api/client-mail').json() == []
    client.post('/api/logout')
    assert client.post('/api/client-mail/sync').status_code == 401


def test_receive_failure_and_oversize_are_visible_without_import(app_client, imap, monkeypatch):
    _, client = app_client
    client.put('/api/client-mail/settings', json=account())
    imap.fail = True
    result = client.post('/api/client-mail/sync')
    assert result.status_code == 502 and 'private server error' not in result.text
    imap.fail = False
    monkeypatch.setattr(mail_sync, 'MAX_BYTES', 100)
    assert client.post('/api/client-mail/sync').json()['skipped'] == 2
    assert client.get('/api/client-mail').json() == []
