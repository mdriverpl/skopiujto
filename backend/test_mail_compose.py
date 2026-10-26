import io
import json
import zipfile

import pyzipper
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from backend import mail_compose, mailer, mail_settings
from backend.test_storage import app_client
from backend.test_access import create_reader, login, READER, ADMIN


@pytest.fixture(autouse=True)
def zip_key(monkeypatch):
    monkeypatch.setenv('EDOCUMENTS_MAIL_SETTINGS_KEY', Fernet.generate_key().decode())


def draft(client):
    result = client.post('/api/client-mail/drafts', json={
        'recipient': 'anna@example.com', 'subject': 'Dokumenty', 'content': 'Pliki w załączniku.'})
    assert result.status_code == 201, result.text
    return result.json()


def attach(client, row, **options):
    files = options.pop('files', [('files', ('umowa.pdf', b'contract', 'application/pdf'))])
    return client.post(f"/api/client-mail/{row['id']}/attachments", data={
        'version': row['version'], **options}, files=files)


def test_plain_and_encrypted_zip_preserve_bytes_and_disambiguate_safe_names():
    parts = [('../umowa.pdf', b'one'), ('C:\\folder\\umowa.pdf', b'two')]
    for secret in ('', 'Zażółć-123!'):
        raw = mail_compose.zip_bytes(parts, secret)
        reader = pyzipper.AESZipFile if secret else zipfile.ZipFile
        with reader(io.BytesIO(raw)) as archive:
            assert archive.namelist() == ['umowa.pdf', 'umowa (2).pdf']
            if secret:
                with pytest.raises(RuntimeError): archive.read('umowa.pdf')
                archive.setpassword(b'wrong')
                with pytest.raises(RuntimeError): archive.read('umowa.pdf')
                archive.setpassword(secret.encode())
            assert archive.read('umowa.pdf') == b'one'
            assert archive.read('umowa (2).pdf') == b'two'


def test_computer_drive_zip_password_send_and_download(app_client, monkeypatch):
    main, client = app_client
    file = client.post('/api/files', files={'file': ('raport.txt', b'report', 'text/plain')}).json()
    row = draft(client)
    response = attach(client, row, drive_ids=json.dumps([file['id']]), zip_enabled='true',
                      zip_name='dokumenty.zip', zip_password='Secret-123!')
    assert response.status_code == 200, response.text
    row = response.json()
    assert {p['name'] for p in row['attachments']} == {'umowa.pdf', 'raport.txt'}
    assert row['zip_password'] == 'Secret-123!' and 'zip_password_secret' not in row
    with main.db() as con:
        stored = con.execute('SELECT zip_password_secret FROM client_mail WHERE id=?', (row['id'],)).fetchone()[0]
        assert stored and 'Secret-123!' not in stored
        # Drive attachments are immutable snapshots, not references to mutable documents.
        con.execute('UPDATE documents SET file=? WHERE id=?', (b'changed', file['id']))
    response = client.get(f"/api/client-mail/{row['id']}/archive")
    assert response.status_code == 200
    with pyzipper.AESZipFile(io.BytesIO(response.content)) as archive:
        archive.setpassword(b'Secret-123!')
        assert archive.read('raport.txt') == b'report'
    calls = []
    monkeypatch.setattr(mail_settings, 'smtp_config', lambda *args: ({'sender': 'sender@example.com'}, 'Sender'))
    monkeypatch.setattr(mailer, 'send_message', lambda *args, **kwargs: calls.append((args, kwargs)))
    result = client.post(f"/api/client-mail/{row['id']}/send", json={'version': row['version']})
    assert result.status_code == 200, result.text
    sent = result.json()
    assert sent['folder'] == 'sent' and sent['zip_password'] == 'Secret-123!'
    assert [a['name'] for a in sent['attachments']] == ['dokumenty.zip']
    args, kwargs = calls[0]
    assert 'Secret-123!' not in args[4]
    assert kwargs['attachments'][0][0] == 'dokumenty.zip'
    raw = kwargs['attachments'][0][1]
    assert client.get(f"/api/client-mail/{sent['id']}/archive").content == raw
    assert client.get(f"/api/client-mail/{sent['id']}/attachments/{sent['attachments'][0]['id']}").content == raw
    assert attach(client, sent).status_code == 409


def test_attachment_validation_removal_conflict_and_failed_smtp_preserve_draft(app_client, monkeypatch):
    _, client = app_client
    row = draft(client)
    assert attach(client, row, zip_password='no-zip').status_code == 422
    assert attach(client, row, drive_ids='{}').status_code == 422
    assert attach(client, row, files=[('files', ('large.bin', b'x' * (mail_compose.MAX_TOTAL + 1)))]).status_code == 422
    saved = attach(client, row).json()
    assert attach(client, row).status_code == 409
    assert len(next(m for m in client.get('/api/client-mail').json() if m['id'] == row['id'])['attachments']) == 1
    monkeypatch.setattr(mail_settings, 'smtp_config', lambda *args: ({'sender': 'sender@example.com'}, 'Sender'))
    def fail(*args, **kwargs): raise HTTPException(503, 'SMTP unavailable')
    monkeypatch.setattr(mailer, 'send_message', fail)
    assert client.post(f"/api/client-mail/{saved['id']}/send", json={'version': saved['version']}).status_code == 503
    listing = next(m for m in client.get('/api/client-mail').json() if m['id'] == row['id'])
    assert listing['folder'] == 'drafts' and len(listing['attachments']) == 1
    removed = attach(client, saved, files=[], remove_ids=json.dumps([saved['attachments'][0]['id']]))
    assert removed.status_code == 200 and removed.json()['attachments'] == []


def test_other_user_cannot_read_password_attach_files_or_copy_private_drive_document(app_client):
    _, client = app_client
    private = client.post('/api/files', files={'file': ('private.txt', b'private')}).json()
    row = attach(client, draft(client), zip_enabled='true', zip_password='Private!').json()
    create_reader(client); login(client, READER)
    assert attach(client, row).status_code == 404
    assert client.get(f"/api/client-mail/{row['id']}/archive").status_code == 404
    assert all(m['id'] != row['id'] for m in client.get('/api/client-mail').json())
    other = draft(client)
    assert attach(client, other, files=[], drive_ids=json.dumps([private['id']])).status_code == 404


def test_group_email_uses_owned_versioned_attachments_and_saves_password_with_sent_mail(app_client, monkeypatch):
    _, client = app_client
    monkeypatch.setattr(mail_settings, 'smtp_config', lambda *args: ({'sender': 'sender@example.com'}, 'Sender'))
    monkeypatch.setattr(mail_settings, 'public_settings', lambda *args: {'smtp': {'configured': True, 'message': ''}})
    calls = []
    monkeypatch.setattr(mailer, 'send_message', lambda *args, **kwargs: calls.append(kwargs['attachments']))
    source = attach(client, draft(client), zip_enabled='true', zip_password='Group-secret!').json()
    body = {'subject': 'Files', 'message': 'Attached', 'channel': 'email', 'source': 'dictionaries',
            'recipients': [], 'direct_email': 'recipient@example.com',
            'attachment_mail_id': source['id'], 'attachment_version': source['version']}
    assert client.post('/api/messages/prepare', json={**body, 'attachment_version': 1}).status_code == 409
    response = client.post('/api/messages/prepare', json=body)
    assert response.status_code == 200, response.text
    plan = response.json()
    result = client.post(f"/api/ai/commands/{plan['id']}/execute", json={'confirmed': True,
        'subject': plan['subject'], 'message': plan['message'], 'recipients': [p['id'] for p in plan['recipients']]})
    assert result.status_code == 200, result.text
    assert result.json()['recipients'][0]['status'] == 'sent'
    assert calls[0][0][0] == 'zalaczniki.zip'
    sent = next(m for m in client.get('/api/client-mail').json() if m['folder'] == 'sent')
    assert sent['zip_password'] == 'Group-secret!' and sent['recipient'] == 'recipient@example.com'


def test_mailer_builds_real_mime_attachments_without_putting_zip_password_in_body(monkeypatch):
    messages = []
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def send_message(self, message, **kwargs): messages.append(message); return {}
        def quit(self): pass
    monkeypatch.setattr(mailer.smtplib, 'SMTP', SMTP)
    mailer.send_message({'host': 'localhost', 'port': 25, 'sender': 'me@example.com', 'security': 'none', 'username': ''},
                        'you@example.com', 'Sender', 'Files', 'Attached', [('raport.pdf', b'pdf bytes')])
    attachment = list(messages[0].iter_attachments())[0]
    assert attachment.get_filename() == 'raport.pdf'
    assert attachment.get_content_type() == 'application/pdf'
    assert attachment.get_payload(decode=True) == b'pdf bytes'
