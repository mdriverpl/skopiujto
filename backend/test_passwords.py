import re
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend import mailer
from backend.test_storage import app_client

@pytest.fixture
def welcome_mail(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, 'configuration', lambda: {'public_url': 'https://docs.example.com'})
    monkeypatch.setattr(mailer, 'send_message', lambda *args: sent.append(args))
    return sent

def test_new_account_email_and_required_password_change(app_client, welcome_mail):
    main, client = app_client
    created = client.post('/api/admin/users', json={'name': 'New User', 'email': 'new@example.com', 'password': 'ignored-password'})
    assert created.status_code == 201, created.text
    account = created.json()
    assert account['email'] == 'new@example.com' and account['must_change_password'] is True
    assert 'password' not in account
    assert len(welcome_mail) == 1 and welcome_mail[0][1] == account['email']
    text = welcome_mail[0][4]
    assert 'https://docs.example.com' in text and 'New User' in text
    temporary = re.search(r'Hasło tymczasowe: (\S+)', text)[1]
    assert temporary not in created.text
    with main.db() as con:
        stored = con.execute('SELECT password FROM users WHERE id=?', (account['id'],)).fetchone()[0]
        assert stored != temporary
    with TestClient(main.app) as newcomer:
        assert newcomer.post('/api/login', json={'name': 'New User', 'password': 'ignored-password'}).status_code == 401
        assert newcomer.post('/api/login', json={'name': 'New User', 'password': temporary}).json()['must_change_password']
        assert newcomer.get('/api/me').status_code == 200
        assert newcomer.get('/api/documents').status_code == 403
        assert newcomer.get('/api/access').status_code == 403
        assert newcomer.post('/api/documents', json={'title': 'Blocked'}).status_code == 403
        assert newcomer.post('/api/me/password', json={'current_password': 'wrong-password', 'new_password': 'new-password-123'}).status_code == 422
        assert newcomer.post('/api/me/password', json={'current_password': temporary, 'new_password': temporary}).status_code == 422
        assert newcomer.post('/api/me/password', json={'current_password': temporary, 'new_password': 'short'}).status_code == 422
        main.initialize()
        assert newcomer.get('/api/me').json()['must_change_password']
        changed = newcomer.post('/api/me/password', json={'current_password': temporary, 'new_password': 'new-password-123'})
        assert changed.status_code == 200 and not changed.json()['must_change_password']
        assert newcomer.get('/api/documents').status_code == 200
        newcomer.post('/api/logout')
        assert newcomer.post('/api/login', json={'name': 'New User', 'password': temporary}).status_code == 401
        assert newcomer.post('/api/login', json={'name': 'New User', 'password': 'new-password-123'}).status_code == 200

def test_self_password_change_revokes_other_sessions(app_client):
    main, client = app_client
    with TestClient(main.app) as other:
        other.post('/api/login', json={'name': 'test-user', 'password': 'test-password-123'})
        previous_cookie = client.cookies.get('session')
        response = client.post('/api/me/password', json={'current_password': 'test-password-123', 'new_password': 'replacement-password-123'})
        assert response.status_code == 200
        assert client.cookies.get('session') != previous_cookie
        assert client.get('/api/me').status_code == 200
        assert other.get('/api/me').status_code == 401
        assert other.post('/api/me/password', json={'current_password': 'replacement-password-123', 'new_password': 'hacked-password-123'}).status_code == 401

def test_failed_mail_rolls_back_creation_and_validation(app_client, welcome_mail, monkeypatch):
    main, client = app_client
    assert client.post('/api/admin/users', json={'name': 'New User', 'email': 'invalid'}).status_code == 422
    assert client.post('/api/admin/users', json={'name': 'New User'}).status_code == 422
    def fail(*args):
        raise HTTPException(503, 'Mail unavailable')
    monkeypatch.setattr(mailer, 'send_message', fail)
    assert client.post('/api/admin/users', json={'name': 'New User', 'email': 'new@example.com'}).status_code == 503
    with main.db() as con:
        assert con.execute('SELECT count(*) FROM users').fetchone()[0] == 1
    assert not welcome_mail

def test_admin_reset_requires_change_and_existing_accounts_stay_unrestricted(app_client):
    _, client = app_client
    account = client.get('/api/me').json()
    assert not account['must_change_password']
    assert client.patch('/api/admin/users/' + account['id'], json={'password': 'reset-password-123'}).status_code == 200
    assert client.get('/api/me').status_code == 401
    assert client.post('/api/login', json={'name': account['name'], 'password': 'reset-password-123'}).json()['must_change_password']
    assert client.get('/api/admin/users').status_code == 403
    assert client.post('/api/logout').status_code == 204
