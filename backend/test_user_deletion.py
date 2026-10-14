import pytest
from fastapi.testclient import TestClient
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, create_account, login
from backend.test_companies import superadmin


def test_delete_revokes_access_and_memberships(app_client):
    main, client = app_client
    superadmin(main)
    account = create_reader(client)
    group = client.post('/api/admin/groups', json={'name': 'Team'}).json()
    folder = client.post('/api/folders', json={'name': 'Shared'}).json()
    client.put(f"/api/admin/groups/{group['id']}/members/{account['id']}")
    with main.db() as con:
        con.execute('INSERT INTO folder_user_permissions VALUES(?,?,1,0,0,0)', (folder['id'], account['id']))
    with TestClient(main.app) as customer:
        assert customer.post('/api/login', json=READER).status_code == 200
        key = customer.post('/api/access-tokens', json={'name': 'Test key'}).json()
        assert client.post(f"/api/admin/users/{account['id']}/impersonate").status_code == 200
        assert client.post('/api/admin/impersonation/stop').status_code == 200
        assert client.delete(f"/api/admin/users/{account['id']}").status_code == 204
        assert customer.get('/api/me').status_code == 401
    assert client.post('/api/login', json=READER).status_code == 401
    with main.db() as con:
        for table in ('users', 'sessions', 'api_access_tokens', 'group_members', 'folder_user_permissions'):
            column = 'id' if table == 'users' else 'user_id'
            assert con.execute(f'SELECT count(*) FROM {table} WHERE {column}=?', (account['id'],)).fetchone()[0] == 0
        assert con.execute('SELECT count(*) FROM impersonation_sessions WHERE target_id=?', (account['id'],)).fetchone()[0] == 0
        assert con.execute('SELECT count(*) FROM impersonation_events WHERE target_id=?', (account['id'],)).fetchone()[0] == 2


def test_delete_protects_self_superadmin_and_last_company_admin(app_client):
    main, client = app_client
    own = client.get('/api/me').json()
    assert client.delete('/api/admin/users/' + own['id']).status_code == 409
    superadmin(main)
    other = client.post('/api/admin/companies', json={'name': 'Other'}).json()
    account = create_account(client, name='other-admin', password='other-admin-password', role='admin', company_id=other['id'])
    assert client.delete('/api/admin/users/' + account['id']).status_code == 409
    reader = create_reader(client, role='admin')
    login(client, READER)
    assert client.delete('/api/admin/users/' + own['id']).status_code == 409
    login(client, ADMIN)
    assert client.delete('/api/admin/users/' + reader['id']).status_code == 204


def test_delete_enforces_company_and_role(app_client):
    main, client = app_client
    superadmin(main)
    company = client.post('/api/admin/companies', json={'name': 'Other'}).json()
    foreign = create_account(client, name='foreign-user', password='foreign-password', company_id=company['id'])
    reader = create_reader(client)
    login(client, READER)
    assert client.delete('/api/admin/users/' + foreign['id']).status_code == 403
    login(client, ADMIN)
    client.patch('/api/admin/users/' + reader['id'], json={'role': 'admin'})
    login(client, READER)
    assert client.delete('/api/admin/users/' + foreign['id']).status_code == 404
    assert client.delete('/api/admin/users/missing').status_code == 404
    login(client, ADMIN)
    assert client.delete('/api/admin/users/' + foreign['id']).status_code == 204


@pytest.mark.parametrize('kind', ['documents', 'notes'])
def test_delete_preserves_linked_data_and_rolls_back_cleanup(app_client, kind):
    main, client = app_client
    account = create_reader(client, can_add=True)
    group = client.post('/api/admin/groups', json={'name': 'Team'}).json()
    client.put(f"/api/admin/groups/{group['id']}/members/{account['id']}")
    with TestClient(main.app) as customer:
        customer.post('/api/login', json=READER)
        record = customer.post('/api/' + kind, json={'title': 'Keep this'}).json()
        response = client.delete('/api/admin/users/' + account['id'])
        assert response.status_code == 409, response.text
        assert customer.get('/api/me').status_code == 200
        assert any(item['id'] == record['id'] for item in customer.get('/api/' + kind).json())
    with main.db() as con:
        assert con.execute('SELECT 1 FROM group_members WHERE user_id=?', (account['id'],)).fetchone()
