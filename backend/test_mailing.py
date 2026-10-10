import io
import smtplib

import pytest
from botocore.response import StreamingBody
from botocore.stub import ANY
from fastapi import HTTPException
from backend import mailer
from backend.test_storage import app_client, s3, put_params
from backend.test_access import ADMIN, READER, create_reader, login

@pytest.fixture
def smtp(monkeypatch):
    for key, value in {'SMTP_HOST': 'smtp.example.com', 'SMTP_FROM': 'documents@example.com',
                       'SMTP_USERNAME': 'test-login', 'SMTP_PASSWORD': 'test-password',
                       'SMTP_PORT': '587', 'SMTP_SECURITY': 'starttls',
                       'EDOCUMENTS_PUBLIC_URL': 'https://documents.example.com'}.items():
        monkeypatch.setenv(key, value)
    sent = []
    monkeypatch.setattr(mailer, 'send_file', lambda *args: sent.append(args))
    return sent

def upload(client, **fields):
    response = client.post('/api/files', data=fields, files={'file': ('contract.txt', b'original-file')})
    assert response.status_code == 201, response.text
    return response.json()

def send(client, doc, recipients=None, **extra):
    return client.post(f"/api/documents/{doc['id']}/emails", json={
        'version': doc['version'], 'recipients': recipients or [{'email': 'anna@example.com', 'name': 'Anna'}],
        'message': 'Proszę o akceptację.', **extra})

def token(smtp, index=0):
    return smtp[index][6].split('/accept/')[1]

def test_send_download_accept_and_sender_status(app_client, smtp):
    main, client = app_client
    doc = upload(client)
    response = send(client, doc, [{'email': 'anna@example.com', 'name': 'Anna'}, {'email': 'jan@example.com'}])
    assert response.status_code == 201, response.text
    assert len(smtp) == 2 and token(smtp, 0) != token(smtp, 1)
    assert smtp[0][4] == b'original-file'
    history = response.json()['history'][0]
    assert len(history['recipients']) == 2
    assert all(person['status'] == 'waiting' for person in history['recipients'])
    assert 'token_hash' not in str(history) and token(smtp) not in str(history)
    with main.db() as c:
        assert c.execute('SELECT token_hash FROM file_mail_recipients WHERE email=?', ('anna@example.com',)).fetchone()[0] == main.digest(token(smtp))
    client.post('/api/logout')
    url = '/api/approvals/' + token(smtp)
    preview = client.get(url)
    assert preview.status_code == 200 and not preview.json()['accepted_at']
    assert preview.headers['cache-control'] == 'no-store'
    assert preview.headers['referrer-policy'] == 'no-referrer'
    assert client.get(url + '/file').content == b'original-file'
    assert not client.get(url).json()['accepted_at']  # Downloads and mail scanners never accept.
    assert client.post(url + '/accept', json={'confirmed': False}).status_code == 422
    accepted = client.post(url + '/accept', json={'confirmed': True})
    assert accepted.status_code == 200 and accepted.json()['accepted_at']
    timestamp = accepted.json()['accepted_at']
    assert client.post(url + '/accept', json={'confirmed': True}).json()['accepted_at'] == timestamp
    login(client, ADMIN)
    listed = client.get('/api/documents').json()[0]
    assert listed['approvals']['accepted'] == 1 and listed['approvals']['waiting'] == 1
    persons = client.get(f"/api/documents/{doc['id']}/emails").json()[0]['recipients']
    assert persons[0]['email'] == 'anna@example.com' and persons[0]['accepted_at'] == timestamp
    assert persons[1]['accepted_at'] is None

def test_sent_snapshot_survives_file_replacement(app_client, smtp):
    _, client = app_client
    doc = upload(client)
    assert send(client, doc).status_code == 201
    assert client.post(f"/api/documents/{doc['id']}/file", files={'file': ('new.txt', b'new-version')}).status_code == 200
    url = '/api/approvals/' + token(smtp)
    assert client.get(url + '/file').content == b'original-file'
    accepted = client.post(url + '/accept', json={'confirmed': True}).json()
    assert accepted['filename'] == 'contract.txt' and accepted['version'] == 1
    history = client.get(f"/api/documents/{doc['id']}/emails").json()[0]
    assert not history['current_version'] and history['recipients'][0]['status'] == 'accepted'
    assert client.get('/api/documents').json()[0]['approvals']['accepted'] == 0

def test_revoke_expire_delete_and_invalid_tokens(app_client, smtp):
    main, client = app_client
    doc = upload(client)
    first = send(client, doc).json()['history'][0]['recipients'][0]
    url = '/api/approvals/' + token(smtp)
    assert client.post(f"/api/documents/{doc['id']}/emails/{first['id']}/revoke").status_code == 204
    assert client.get(url).status_code == 410
    assert client.get(url + '/file').status_code == 410
    assert client.post(url + '/accept', json={'confirmed': True}).status_code == 410
    assert send(client, doc).status_code == 201
    expired = '/api/approvals/' + token(smtp, 1)
    with main.db() as c:
        c.execute('UPDATE file_mailings SET expires=0 WHERE id=(SELECT mailing_id FROM file_mail_recipients WHERE token_hash=?)', (main.digest(token(smtp, 1)),))
    assert client.get(expired).status_code == 410
    assert client.post(expired + '/accept', json={'confirmed': True}).status_code == 410
    assert client.get('/api/approvals/invalid').status_code == 404
    assert send(client, doc).status_code == 201
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get('/api/approvals/' + token(smtp, 2)).status_code == 404
    with main.db() as c:
        assert c.execute('SELECT count(*) FROM file_mailings').fetchone()[0] == 0
        assert c.execute('SELECT count(*) FROM file_mail_recipients').fetchone()[0] == 0

def test_permissions_own_read_only_shared_admin_and_graphics(app_client, smtp):
    _, client = app_client
    reader = create_reader(client, can_add=True, can_edit=True, role='admin')
    folder = client.post('/api/folders', json={'name': 'Shared', 'access_mode': 'users', 'user_ids': [reader['id']], 'can_edit': True}).json()
    doc = upload(client, folder_id=folder['id'])
    assert send(client, doc).status_code == 201
    login(client, READER)
    listed = client.get('/api/documents').json()[0]
    assert not listed['permissions']['send'] and 'approvals' not in listed
    assert send(client, doc).status_code == 403
    assert client.get(f"/api/documents/{doc['id']}/emails").status_code == 403
    own = client.post('/api/files', files={'file': ('photo.png', b'graphic-bytes')}).json()
    assert own['permissions']['send'] and not own['permissions']['edit']
    assert send(client, own).status_code == 201
    login(client, ADMIN)
    assert client.patch(f"/api/admin/users/{reader['id']}", json={'can_edit': False}).status_code == 200
    login(client, READER)
    assert send(client, own).status_code == 403
    assert client.get(f"/api/documents/{own['id']}/emails").status_code == 200
    client.post('/api/logout')
    assert send(client, own).status_code == 401

@pytest.mark.parametrize('body', [
    {'recipients': [{'email': 'bad-email'}]},
    {'recipients': [{'email': 'anna@example.com'}, {'email': 'ANNA@example.com'}]},
    {'recipients': [{'email': 'anna@example.com\r\nBcc: bad@example.com'}]},
    {'days': 31}, {'version': 99},
])
def test_invalid_input_sends_nothing(app_client, smtp, body):
    main, client = app_client
    response = send(client, upload(client), **body)
    assert response.status_code in (422, 409)
    assert smtp == []
    with main.db() as c:
        assert c.execute('SELECT count(*) FROM file_mailings').fetchone()[0] == 0

def test_missing_smtp_configuration_creates_no_links(app_client, smtp, monkeypatch):
    main, client = app_client
    monkeypatch.delenv('SMTP_HOST')
    assert not client.get('/api/email-settings').json()['configured']
    assert send(client, upload(client)).status_code == 503
    assert not smtp
    with main.db() as c:
        assert c.execute('SELECT count(*) FROM file_mailings').fetchone()[0] == 0

def test_partial_smtp_failure_and_no_false_acceptance(app_client, smtp, monkeypatch):
    _, client = app_client
    def fake_send(*args):
        smtp.append(args)
        if args[1]['email'] == 'jan@example.com':
            raise HTTPException(503, 'Nie potwierdzono wysyłki.')
    monkeypatch.setattr(mailer, 'send_file', fake_send)
    doc = upload(client)
    response = send(client, doc, [{'email': 'anna@example.com'}, {'email': 'jan@example.com'}])
    assert response.status_code == 201
    persons = response.json()['history'][0]['recipients']
    assert persons[0]['status'] == 'waiting' and persons[1]['status'] == 'failed'
    assert client.get('/api/approvals/' + token(smtp, 1)).status_code == 410
    assert client.post('/api/approvals/' + token(smtp, 1) + '/accept', json={'confirmed': True}).status_code == 410

def test_s3_snapshot_download_and_cleanup(s3, smtp):
    main, client, stub = s3
    data = b'original-file'
    stub.add_response('put_object', {}, put_params(data))
    doc = upload(client)
    with main.db() as c:
        original_key = c.execute('SELECT object_key FROM documents WHERE id=?', (doc['id'],)).fetchone()[0]
    stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(data), len(data))}, {'Bucket': 'private-test-bucket', 'Key': original_key})
    stub.add_response('put_object', {}, put_params(data))
    assert send(client, doc).status_code == 201
    with main.db() as c:
        snapshot = c.execute('SELECT file,object_key FROM file_mailings').fetchone()
        assert snapshot['file'] is None and snapshot['object_key'] != original_key
    stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(data), len(data))}, {'Bucket': 'private-test-bucket', 'Key': snapshot['object_key']})
    assert client.get('/api/approvals/' + token(smtp) + '/file').content == data
    stub.add_response('delete_object', {}, {'Bucket': 'private-test-bucket', 'Key': original_key})
    stub.add_response('delete_object', {}, {'Bucket': 'private-test-bucket', 'Key': snapshot['object_key']})
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204

def test_smtp_tls_attachment_envelope_and_quit_failure(monkeypatch):
    state = {}
    class FakeSMTP:
        def __init__(self, host, port, **kwargs): state['connection'] = (host, port, kwargs)
        def starttls(self, **kwargs): state['tls'] = kwargs['context']
        def login(self, username, password): state['login'] = (username, password)
        def send_message(self, message, **kwargs): state['message'] = message; state['envelope'] = kwargs; return {}
        def quit(self): raise smtplib.SMTPServerDisconnected('test')
        def close(self): state['closed'] = True
    monkeypatch.setattr(mailer.smtplib, 'SMTP', FakeSMTP)
    config = {'host': 'smtp.example.com', 'port': 587, 'sender': 'docs@example.com', 'security': 'starttls', 'username': 'login', 'password': 'password'}
    mailer.send_file(config, {'email': 'anna@example.com'}, 'Autor', 'umowa.txt', b'original-file', 1,
                     'https://docs.example.com/accept/random-token', 'Wiadomość', '2026-10-17 10:00')
    message = state['message']
    assert state['tls'].check_hostname and state['login'] == ('login', 'password')
    assert state['envelope'] == {'from_addr': 'docs@example.com', 'to_addrs': ['anna@example.com']}
    assert list(message.iter_attachments())[0].get_payload(decode=True) == b'original-file'
    assert '/accept/random-token' in message.get_body(preferencelist=('plain',)).get_content()
    assert state['closed']  # Successful DATA is still recorded even when QUIT fails.
