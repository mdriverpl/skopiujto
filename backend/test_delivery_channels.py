import json
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi import HTTPException

from backend import mailer, sms
from backend.test_storage import app_client
from backend.test_mailing import smtp, upload, send, token
from backend.test_access import ADMIN, READER, create_reader, login


@pytest.fixture
def sms_provider(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr(sms, 'ENV_FILE', tmp_path / '.env')
    for name, value in {'SMSAPI_TOKEN': 'test-sms-private-token', 'SMSAPI_SENDER': 'Documents',
                        'EDOCUMENTS_PUBLIC_URL': 'https://documents.example.com'}.items(): monkeypatch.setenv(name, value)
    calls = []
    result = {'status': 200, 'json': {'count': 1, 'list': [{'id': 'sms-id', 'number': '48600123456', 'status': 'QUEUE'}]}, 'exception': None}
    def handle(request):
        calls.append(request)
        if result['exception']: raise result['exception']
        return httpx.Response(result['status'], json=result['json'])
    original = httpx.Client
    monkeypatch.setattr(sms.httpx, 'Client', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)))
    return calls, result


def test_internal_delivery_without_smtp_and_recipient_only_snapshot_access(app_client, monkeypatch):
    main, client = app_client
    reader = create_reader(client)
    doc = upload(client)
    monkeypatch.setattr(mailer, 'configuration', lambda: (_ for _ in ()).throw(AssertionError('SMTP must not be used')))
    response = send(client, doc, [{'channel': 'user', 'user_id': reader['id'], 'name': 'Spoofed name'}])
    assert response.status_code == 201, response.text
    person = response.json()['history'][0]['recipients'][0]
    assert person['channel'] == 'user' and person['name'] == READER['name'] and person['status'] == 'waiting'
    assert client.get('/api/approval-inbox').json() == []
    url = '/api/approval-inbox/' + person['id']
    assert client.get(url + '/file').status_code == 404
    assert client.post(url + '/accept', json={'confirmed': True}).status_code == 404
    # Replacing the original never changes the received snapshot.
    assert client.post(f"/api/documents/{doc['id']}/file", files={'file': ('new.txt', b'new-file')}).status_code == 200
    main.initialize()
    login(client, READER)
    inbox = client.get('/api/approval-inbox').json()
    assert len(inbox) == 1 and inbox[0]['id'] == person['id'] and inbox[0]['version'] == 1
    assert client.get('/api/documents').json() == []
    assert client.get(url + '/file').content == b'original-file'
    assert not client.get('/api/approval-inbox').json()[0]['accepted_at']
    assert client.post(url + '/accept', json={'confirmed': False}).status_code == 422
    accepted = client.post(url + '/accept', json={'confirmed': True})
    assert accepted.status_code == 200 and accepted.json()['accepted_at']
    timestamp = accepted.json()['accepted_at']
    assert client.post(url + '/accept', json={'confirmed': True}).json()['accepted_at'] == timestamp
    login(client, ADMIN)
    history = client.get(f"/api/documents/{doc['id']}/emails").json()[0]
    assert history['recipients'][0]['status'] == 'accepted' and not history['current_version']
    client.post('/api/logout')
    assert client.get('/api/approval-inbox').status_code == 401
    assert client.get(url + '/file').status_code == 401


@pytest.mark.parametrize('action', ['revoke', 'expire', 'disable_sender', 'delete_document'])
def test_internal_access_ends_when_revoked_expired_sender_disabled_or_document_deleted(app_client, action):
    main, client = app_client
    reader = create_reader(client)
    sender = client.get('/api/me').json()
    doc = upload(client)
    person = send(client, doc, [{'channel': 'user', 'user_id': reader['id']}]).json()['history'][0]['recipients'][0]
    if action == 'revoke': assert client.post(f"/api/documents/{doc['id']}/emails/{person['id']}/revoke").status_code == 204
    if action == 'expire':
        with main.db() as con: con.execute('UPDATE file_mailings SET expires=0')
    if action == 'disable_sender':
        with main.db() as con: con.execute('UPDATE users SET active=0 WHERE id=?', (sender['id'],))
    if action == 'delete_document': assert client.delete('/api/documents/' + doc['id']).status_code == 204
    login(client, READER)
    url = '/api/approval-inbox/' + person['id']
    expected = 404 if action in ('disable_sender', 'delete_document') else 410
    assert client.get(url + '/file').status_code == expected
    assert client.post(url + '/accept', json={'confirmed': True}).status_code == expected


def test_mixed_email_sms_and_internal_delivery_has_separate_acceptances(app_client, smtp, sms_provider):
    main, client = app_client
    calls, _ = sms_provider
    reader = create_reader(client)
    doc = upload(client)
    result = send(client, doc, [{'email': 'anna@example.com'}, {'channel': 'sms', 'phone': '600 123 456'},
                              {'channel': 'user', 'user_id': reader['id']}])
    assert result.status_code == 201, result.text
    people = result.json()['history'][0]['recipients']
    assert [person['channel'] for person in people] == ['email', 'sms', 'user']
    assert all(person['status'] == 'waiting' for person in people)
    assert people[1]['phone'] == '+48600123456'
    assert len(smtp) == 1 and len(calls) == 1
    params = parse_qs(calls[0].content.decode())
    assert str(calls[0].url) == 'https://api.smsapi.pl/sms.do'
    assert calls[0].headers['Authorization'] == 'Bearer test-sms-private-token'
    assert params['to'] == ['48600123456'] and params['from'] == ['Documents']
    sms_token = params['message'][0].split('/accept/')[1].split('\n')[0]
    assert token(smtp) != sms_token
    with main.db() as con:
        assert con.execute("SELECT provider_id FROM file_mail_recipients WHERE channel='sms'").fetchone()[0] == 'sms-id'
    client.post('/api/logout')
    preview = client.get('/api/approvals/' + sms_token)
    assert preview.status_code == 200 and preview.json()['channel'] == 'sms'
    assert client.get('/api/approvals/' + sms_token + '/file').content == b'original-file'
    assert client.post('/api/approvals/' + sms_token + '/accept', json={'confirmed': True}).status_code == 200
    login(client, ADMIN)
    statuses = client.get('/api/documents').json()[0]['approvals']
    assert statuses['accepted'] == 1 and statuses['waiting'] == 2


@pytest.mark.parametrize('bad', [
    {'error': 101, 'message': 'secret provider diagnostics'}, {'count': 0, 'list': []},
    {'count': 1, 'list': [{'id': 'x', 'number': 'wrong-number'}]},
])
def test_failed_sms_has_no_usable_link_and_does_not_block_internal_delivery(app_client, sms_provider, bad):
    main, client = app_client
    calls, result = sms_provider
    result['json'] = bad
    reader = create_reader(client)
    doc = upload(client)
    response = send(client, doc, [{'channel': 'sms', 'phone': '+48600123456'}, {'channel': 'user', 'user_id': reader['id']}])
    assert response.status_code == 201
    assert [person['status'] for person in response.json()['history'][0]['recipients']] == ['failed', 'waiting']
    assert 'secret provider diagnostics' not in response.text
    sms_token = parse_qs(calls[0].content.decode())['message'][0].split('/accept/')[1].split('\n')[0]
    assert client.get('/api/approvals/' + sms_token).status_code == 410
    assert client.post('/api/approvals/' + sms_token + '/accept', json={'confirmed': True}).status_code == 410


def test_sms_configuration_is_private_and_missing_configuration_creates_no_mailing(app_client, sms_provider, monkeypatch):
    _, client = app_client
    calls, _ = sms_provider
    status = client.get('/api/approval-settings')
    assert status.json()['sms']['configured'] and status.json()['user']['configured']
    assert 'test-sms-private-token' not in status.text
    monkeypatch.delenv('SMSAPI_TOKEN')
    assert not client.get('/api/approval-settings').json()['sms']['configured']
    doc = upload(client)
    assert send(client, doc, [{'channel': 'sms', 'phone': '+48600123456'}]).status_code == 503
    assert client.get(f"/api/documents/{doc['id']}/emails").json() == []
    assert calls == []


@pytest.mark.parametrize('recipients', [
    [{'channel': 'sms', 'phone': 'abc'}], [{'channel': 'sms', 'phone': '+123'}],
    [{'channel': 'sms', 'phone': '600 123 456'}, {'channel': 'sms', 'phone': '+48 600 123 456'}],
    [{'channel': 'user'}], [{'channel': 'user', 'user_id': 'missing'}],
    [{'channel': 'fax', 'email': 'anna@example.com'}],
])
def test_invalid_recipients_never_create_delivery(app_client, recipients):
    _, client = app_client
    doc = upload(client)
    assert send(client, doc, recipients).status_code == 422
    assert client.get(f"/api/documents/{doc['id']}/emails").json() == []


def test_inactive_internal_recipient_is_rejected(app_client):
    _, client = app_client
    reader = create_reader(client)
    client.patch('/api/admin/users/' + reader['id'], json={'active': False})
    doc = upload(client)
    assert send(client, doc, [{'channel': 'user', 'user_id': reader['id']}]).status_code == 422


def test_sms_timeout_is_not_retried_and_keeps_provider_error_private(app_client, sms_provider):
    _, client = app_client
    calls, result = sms_provider
    result['exception'] = httpx.ReadTimeout('test-private-diagnostic')
    with pytest.raises(HTTPException) as error:
        sms.send_link(sms.configuration(), '+48600123456', 'file.txt', 1, 'https://docs.example/accept/token', 7)
    assert len(calls) == 1 and 'test-private-diagnostic' not in error.value.detail
