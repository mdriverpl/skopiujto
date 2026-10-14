import pytest
from backend import companies, database, access
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, create_account, login

def superadmin(main):
    with main.db() as con:
        con.execute("UPDATE users SET is_superadmin=1 WHERE name=?", (ADMIN['name'],))

def test_directory_is_superadmin_only_and_default_company_is_migrated(app_client):
    main, client = app_client
    own = client.get('/api/me/company').json()
    assert own['id'] == companies.DEFAULT_COMPANY_ID
    assert client.get('/api/me').json()['company_id'] == own['id']
    assert client.get('/api/admin/companies').status_code == 403
    assert client.post('/api/admin/companies', json={'name': 'Company A'}).status_code == 403
    superadmin(main)
    listing = client.get('/api/admin/companies').json()
    assert listing[0]['user_count'] == 1
    added = client.post('/api/admin/companies', json={'name': '  Company A  ', 'nip': '123', 'email': 'office@example.com'})
    assert added.status_code == 201 and added.json()['name'] == 'Company A'
    item = added.json()
    assert client.patch('/api/admin/companies/' + item['id'], json={**item, 'name': 'Company A1'}).json()['version'] == 2
    assert client.patch('/api/admin/companies/' + item['id'], json=item).status_code == 409
    assert client.delete('/api/admin/companies/' + own['id']).status_code == 409
    assert client.delete('/api/admin/companies/' + item['id']).status_code == 204
    client.post('/api/logout')
    assert client.get('/api/admin/companies').status_code == 401

def test_company_assignments_are_required_and_admin_is_limited_to_own_company(app_client):
    main, client = app_client
    superadmin(main)
    another = client.post('/api/admin/companies', json={'name': 'Other company'}).json()
    first = create_reader(client, role='admin')
    second = create_account(client, name='other-admin', password='other-admin-password', role='admin', company_id=another['id'])
    assert second['company_id'] == another['id']
    assert client.delete('/api/admin/companies/' + another['id']).status_code == 409
    login(client, READER)
    visible = client.get('/api/admin/users').json()
    assert first['id'] in {item['id'] for item in visible}
    assert second['id'] not in {item['id'] for item in visible}
    assert client.patch('/api/admin/users/' + second['id'], json={'name': 'Changed'}).status_code == 404
    assert client.patch('/api/admin/users/' + first['id'], json={'company_id': another['id']}).status_code == 403
    assert client.patch('/api/admin/users/' + client.get('/api/admin/users').json()[0]['id'], json={'is_superadmin': True}).status_code in (200, 404)
    assert not client.get('/api/me').json()['is_superadmin']
    assert client.get('/api/admin/companies').status_code == 403
    assert client.get('/api/me/company').json()['id'] == companies.DEFAULT_COMPANY_ID

def test_moving_user_removes_group_memberships_and_revokes_sessions(app_client):
    main, client = app_client
    superadmin(main)
    account = create_reader(client)
    group = client.post('/api/admin/groups', json={'name': 'Team'}).json()
    assert client.put(f"/api/admin/groups/{group['id']}/members/{account['id']}").status_code == 204
    company = client.post('/api/admin/companies', json={'name': 'Destination'}).json()
    result = client.patch('/api/admin/users/' + account['id'], json={'company_id': company['id']})
    assert result.status_code == 200 and result.json()['company_id'] == company['id']
    with main.db() as con:
        assert con.execute('SELECT count(*) FROM group_members WHERE user_id=?', (account['id'],)).fetchone()[0] == 0
        assert con.execute('SELECT count(*) FROM sessions WHERE user_id=?', (account['id'],)).fetchone()[0] == 0
    assert client.put(f"/api/admin/groups/{group['id']}/members/{account['id']}").status_code == 404

def test_superadmin_binding_is_single_and_survives_email_and_selector_changes(app_client, monkeypatch):
    main, client = app_client
    reader = create_reader(client)
    monkeypatch.setenv('EDOCUMENTS_SUPERADMIN_ACCOUNT', ADMIN['name'])
    with main.db() as con: companies.bind_superadmin(con)
    current = client.get('/api/me').json()
    assert current['is_superadmin']
    assert client.patch('/api/admin/users/' + current['id'], json={'role': 'user'}).status_code == 409
    assert client.patch('/api/admin/users/' + current['id'], json={'active': False}).status_code == 409
    monkeypatch.setenv('EDOCUMENTS_SUPERADMIN_ACCOUNT', READER['name'])
    with main.db() as con:
        companies.bind_superadmin(con)
        assert con.execute('SELECT count(*) FROM users WHERE is_superadmin=1').fetchone()[0] == 1
    with pytest.raises(database.IntegrityError):
        with main.db() as con: con.execute('UPDATE users SET is_superadmin=1 WHERE id=?', (reader['id'],))
    login(client, READER)
    assert not client.get('/api/me').json()['is_superadmin']
    assert client.patch('/api/admin/users/' + current['id'], json={'password': 'takeover-password'}).status_code == 403

def test_group_names_and_grants_are_company_scoped(app_client):
    main, client = app_client
    superadmin(main)
    other = client.post('/api/admin/companies', json={'name': 'Another'}).json()
    reader = create_reader(client, role='admin', can_add=True)
    member = create_account(client, name='another-member', password='another-member-password', role='admin', company_id=other['id'])
    own = client.post('/api/admin/groups', json={'name': 'Accounting'}).json()
    remote = client.post('/api/admin/groups', json={'name': 'Accounting', 'company_id': other['id']})
    assert remote.status_code == 201
    assert client.put(f"/api/admin/groups/{own['id']}/members/{member['id']}").status_code == 404
    folder = client.post('/api/folders', json={'name': 'Private folder'}).json()
    assert client.put(f"/api/admin/groups/{remote.json()['id']}/permissions", json={'folder_id': folder['id']}).status_code == 404
    login(client, READER)
    assert all(item['company_id'] == reader['company_id'] for item in client.get('/api/admin/groups').json())
    assert client.delete('/api/admin/groups/' + remote.json()['id']).status_code == 404

def test_company_migration_is_repeatable(app_client):
    main, client = app_client
    first = client.get('/api/me').json()['company_id']
    main.initialize()
    main.initialize()
    assert client.get('/api/me').json()['company_id'] == first
    with main.db() as con:
        assert con.execute('SELECT count(*) FROM users WHERE company_id IS NULL').fetchone()[0] == 0

def test_root_group_grant_does_not_cross_company_boundary(app_client):
    main, client = app_client
    superadmin(main)
    other = client.post('/api/admin/companies', json={'name': 'Remote company'}).json()
    reader = create_reader(client)
    foreign = create_account(client, name='foreign-owner', password='foreign-owner-password', company_id=other['id'])
    group = client.post('/api/admin/groups', json={'name': 'Root readers'}).json()
    assert client.put(f"/api/admin/groups/{group['id']}/members/{reader['id']}").status_code == 204
    assert client.put(f"/api/admin/groups/{group['id']}/permissions", json={'can_read': True}).status_code == 200
    with main.db() as con:
        owner = con.execute('SELECT id FROM users WHERE name=?', (ADMIN['name'],)).fetchone()['id']
        assert access.permissions(con, reader, None, owner)['read']
        assert not access.permissions(con, reader, None, foreign['id'])['read']
