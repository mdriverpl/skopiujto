import base64
import json
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from backend import webpush
from backend.test_storage import app_client
from backend.test_access import READER, create_reader


@pytest.fixture
def push_config(monkeypatch):
    for key in ('PRIVATE_KEY', 'PUBLIC_KEY', 'SUBJECT'):
        monkeypatch.setenv('EDOCUMENTS_WEBPUSH_' + key, 'test-' + key)
    monkeypatch.setenv('EDOCUMENTS_WEBPUSH_WORKER', '0')


def payload(suffix='test'):
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
    public = ec.generate_private_key(ec.SECP256R1()).public_key()
    return {'endpoint': 'https://fcm.googleapis.com/fcm/send/' + suffix, 'name': 'Windows',
            'keys': {'p256dh': encode(public.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)),
                     'auth': encode(b'0123456789abcdef')}}


def subscribe(client, suffix='test', **preferences):
    response = client.post('/api/push/subscriptions', json={**payload(suffix), **preferences})
    assert response.status_code == 201, response.text
    return response.json()['id']


def insert_message(main, owner, identifier, timestamp):
    with main.db() as con:
        con.execute('''INSERT INTO user_messages(id,sender_id,recipient_id,subject,message,created_at)
            VALUES(?,?,?,?,?,?)''', (identifier, owner, owner, 'Private title', 'Private body',
                                   datetime.fromtimestamp(timestamp, timezone.utc).isoformat()))


def test_config_no_secrets_and_authenticated_only(app_client, push_config):
    _, client = app_client
    result = client.get('/api/push/config')
    assert result.json() == {'configured': True, 'public_key': 'test-PUBLIC_KEY'}
    assert 'PRIVATE_KEY' not in result.text
    client.post('/api/logout')
    assert client.get('/api/push/config').status_code == 401
    assert client.get('/api/push/subscriptions').status_code == 401


def test_subscribe_dedup_preferences_and_logout(app_client, push_config):
    main, client = app_client
    body = payload()
    first = client.post('/api/push/subscriptions', json=body).json()['id']
    assert client.post('/api/push/subscriptions', json=body).json()['id'] == first
    assert len(client.get('/api/push/subscriptions').json()) == 1
    response = client.patch('/api/push/subscriptions/' + first, json={'messages': False, 'tasks': True, 'reminders': False})
    assert response.status_code == 200
    row = client.get('/api/push/subscriptions').json()[0]
    assert not row['messages'] and not row['reminders']
    assert 'endpoint' not in row and 'subscription' not in row and 'session_token' not in row
    client.post('/api/logout')
    with main.db() as con:
        assert not con.execute('SELECT 1 FROM push_subscriptions').fetchone()


@pytest.mark.parametrize('endpoint', [
    'http://127.0.0.1:8000/api/setup', 'https://127.0.0.1/',
    'https://fcm.googleapis.com.attacker.example/', 'https://evil.example/',
    'https://fcm.googleapis.com:1234/', 'https://user@fcm.googleapis.com/',
    'https://notify.windows.com.attacker.example/'
])
def test_rejects_arbitrary_endpoints(app_client, push_config, endpoint):
    _, client = app_client
    assert client.post('/api/push/subscriptions', json={**payload(), 'endpoint': endpoint}).status_code == 422


def test_windows_edge_endpoint_and_malformed_keys(app_client, push_config):
    _, client = app_client
    body = {**payload(), 'endpoint': 'https://wns2-example.notify.windows.com/w/?token=test'}
    assert client.post('/api/push/subscriptions', json=body).status_code == 201
    assert client.post('/api/push/subscriptions', json={**payload('bad'), 'keys': {'auth': 'bad'}}).status_code == 422


def test_account_isolation_and_remote_revoke(app_client, push_config):
    _, client = app_client
    create_reader(client)
    identifier = subscribe(client)
    with TestClient(client.app) as reader:
        assert reader.post('/api/login', json=READER).status_code == 200
        assert reader.get('/api/push/subscriptions').json() == []
        assert reader.patch('/api/push/subscriptions/' + identifier, json={}).status_code == 404
        assert reader.post('/api/push/subscriptions/' + identifier + '/test').status_code == 404
        reader.delete('/api/push/subscriptions/' + identifier)
        assert len(client.get('/api/push/subscriptions').json()) == 1
        assert reader.post('/api/push/subscriptions', json=payload()).status_code == 409
    assert client.delete('/api/push/subscriptions/' + identifier).status_code == 204
    assert client.get('/api/push/subscriptions').json() == []


def test_new_messages_deduplicated_and_old_messages_skipped(app_client, push_config, monkeypatch):
    main, client = app_client
    owner = client.get('/api/me').json()['id']
    now = time.time()
    insert_message(main, owner, 'old', now - 60)
    subscribe(client)
    insert_message(main, owner, 'new', now + 1)
    sent = []
    monkeypatch.setattr(webpush, 'send', lambda sub, body: sent.append((sub, body)))
    webpush.dispatch(main.db, now + 2)
    webpush.dispatch(main.db, now + 3)
    assert len(sent) == 1
    assert sent[0][1]['url'] == '/?section=mail'
    assert 'Private' not in json.dumps(sent[0][1])


def test_retries_expired_subscription_and_read_message_cancellation(app_client, push_config, monkeypatch):
    main, client = app_client
    owner = client.get('/api/me').json()['id']
    subscribe(client)
    now = time.time() + 1
    insert_message(main, owner, 'new', now)
    attempts = []
    def fail(sub, body):
        attempts.append(body)
        raise RuntimeError('network unavailable')
    monkeypatch.setattr(webpush, 'send', fail)
    webpush.dispatch(main.db, now + 1)
    webpush.dispatch(main.db, now + 2)
    assert len(attempts) == 1
    with main.db() as con:
        con.execute("UPDATE user_messages SET read_at='read' WHERE id='new'")
    webpush.dispatch(main.db, now + 100)
    assert len(attempts) == 1
    insert_message(main, owner, 'expired', now + 101)
    def gone(sub, body):
        error = RuntimeError('expired')
        error.response = SimpleNamespace(status_code=410)
        raise error
    monkeypatch.setattr(webpush, 'send', gone)
    webpush.dispatch(main.db, now + 102)
    assert client.get('/api/push/subscriptions').json() == []


def test_due_reminders_and_completed_task_not_delivered(app_client, push_config, monkeypatch):
    main, client = app_client
    owner = client.get('/api/me').json()['id']
    subscribe(client, tasks=False, messages=False)
    now = time.time() + 1
    task = client.post('/api/tasks', json={'title': 'Secret task', 'assignee_id': owner,
        'due_at': datetime.fromtimestamp(now + 7200, timezone.utc).isoformat()})
    assert task.status_code == 201, task.text
    sent = []
    monkeypatch.setattr(webpush, 'send', lambda sub, body: sent.append(body))
    webpush.dispatch(main.db, now)
    webpush.dispatch(main.db, now + 1)
    assert len(sent) == 1 and '24' in sent[0]['body']
    webpush.dispatch(main.db, now + 4000)
    assert len(sent) == 2 and 'godzinę' in sent[1]['body']
    with main.db() as con:
        con.execute("UPDATE user_tasks SET status='done' WHERE id=?", (task.json()['id'],))
    webpush.dispatch(main.db, now + 5000)
    assert len(sent) == 2


def test_disabled_account_and_expired_session_stop_sending(app_client, push_config, monkeypatch):
    main, client = app_client
    owner = client.get('/api/me').json()['id']
    subscribe(client)
    now = time.time() + 1
    insert_message(main, owner, 'new', now)
    sent = []
    monkeypatch.setattr(webpush, 'send', lambda sub, body: sent.append(body))
    with main.db() as con:
        con.execute('UPDATE users SET active=0 WHERE id=?', (owner,))
    webpush.dispatch(main.db, now + 1)
    assert sent == []
    with main.db() as con:
        con.execute('UPDATE users SET active=1 WHERE id=?', (owner,))
        con.execute('UPDATE sessions SET expires=? WHERE user_id=?', (now - 10, owner))
    webpush.dispatch(main.db, now + 2)
    assert sent == []


def test_missing_configuration_keeps_installation_but_blocks_push(app_client, monkeypatch):
    _, client = app_client
    for key in ('PRIVATE_KEY', 'PUBLIC_KEY', 'SUBJECT'):
        monkeypatch.delenv('EDOCUMENTS_WEBPUSH_' + key, raising=False)
    assert client.get('/api/push/config').json() == {'configured': False, 'public_key': ''}
    assert client.post('/api/push/subscriptions', json=payload()).status_code == 503

def test_direct_account_switch_detaches_old_browser_push(app_client, push_config):
    _, client = app_client
    create_reader(client)
    subscribe(client)
    assert client.post('/api/login', json=READER).status_code == 200
    assert client.get('/api/push/subscriptions').json() == []
    assert client.post('/api/push/subscriptions', json=payload()).status_code == 201
