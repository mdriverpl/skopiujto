import pytest
import re
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import mailer
from backend.test_storage import app_client

ADMIN = {'name': 'test-user', 'password': 'test-password-123'}
READER = {'name': 'reader', 'password': 'reader-password-123'}

def login(client, credentials):
    client.post('/api/logout')
    response = client.post('/api/login', json=credentials)
    assert response.status_code == 200
    return response.json()

def create_reader(client, **extra):
    return create_account(client, **{**READER, **extra})

def create_account(client, name, password, **extra):
    with patch.object(mailer, 'configuration', return_value={'public_url': 'https://example.com'}), patch.object(mailer, 'send_message') as send:
        response = client.post('/api/admin/users', json={'name': name, 'email': 'reader@example.com', **extra})
    assert response.status_code == 201, response.text
    temporary = re.search(r'Hasło tymczasowe: (\S+)', send.call_args.args[4])[1]
    with TestClient(client.app) as newcomer:
        assert newcomer.post('/api/login', json={'name': name, 'password': temporary}).status_code == 200
        changed = newcomer.post('/api/me/password', json={'current_password': temporary, 'new_password': password})
        assert changed.status_code == 200, changed.text
    return changed.json()

def make_shared(client, reader, rights):
    parent = client.post('/api/folders', json={'name': 'Parent'}).json()
    folder = client.post('/api/folders', json={'name': 'Shared', 'parent_id': parent['id']}).json()
    child = client.post('/api/folders', json={'name': 'Child', 'parent_id': folder['id']}).json()
    doc = client.post('/api/documents', json={'title': 'Contract', 'folder_id': child['id']}).json()
    group = client.post('/api/admin/groups', json={'name': 'Team'}).json()
    assert client.put(f"/api/admin/groups/{group['id']}/members/{reader['id']}").status_code == 204
    assert client.put(f"/api/admin/groups/{group['id']}/permissions", json={'folder_id': folder['id'], **rights}).status_code == 200
    return parent, folder, child, doc, group

def test_admin_accounts_and_session_revocation(app_client):
    main, client = app_client
    assert client.get('/api/me').json()['role'] == 'admin'
    reader = create_reader(client)
    assert 'password' not in reader
    assert not reader['can_edit'] and not reader['can_add'] and not reader['can_delete']
    with patch.object(mailer, 'configuration', return_value={'public_url': 'https://example.com'}):
        assert client.post('/api/admin/users', json={'name': READER['name'], 'email': 'reader@example.com'}).status_code == 409
    login(client, READER)
    assert client.get('/api/admin/users').status_code == 403
    assert client.get('/api/admin/groups').status_code == 403
    assert client.post('/api/admin/groups', json={'name': 'Hacked'}).status_code == 403
    assert client.patch(f"/api/admin/users/{reader['id']}", json={'role': 'admin'}).status_code == 403
    assert client.post('/api/files', files={'file': ('test.txt', b'test')}).status_code == 403
    assert client.post('/api/documents', json={'title': 'test'}).status_code == 403
    assert client.post('/api/folders', json={'name': 'test'}).status_code == 403
    login(client, ADMIN)
    assert client.patch(f"/api/admin/users/{reader['id']}", json={'active': False}).status_code == 200
    assert client.post('/api/login', json=READER).status_code == 401
    assert client.patch(f"/api/admin/users/{reader['id']}", json={'active': True}).status_code == 200
    login(client, READER)
    with main.db() as con:
        con.execute('UPDATE users SET active=0 WHERE id=?', (reader['id'],))
    assert client.get('/api/me').status_code == 401

@pytest.mark.parametrize('right', ['can_read', 'can_edit', 'can_add', 'can_delete'])
def test_scoped_permissions_enforced_on_every_action(app_client, right):
    main, client = app_client
    reader = create_reader(client)
    parent, folder, child, doc, group = make_shared(client, reader, {right: True})
    private = client.post('/api/documents', json={'title': 'Private'}).json()
    deadline = client.post(f"/api/documents/{doc['id']}/deadlines", json={'title': 'Due', 'due_at': '2030-01-01T00:00:00+00:00'}).json()['deadlines'][0]
    login(client, READER)
    visible = client.get('/api/documents').json()
    assert [item['id'] for item in visible] == [doc['id']]
    assert client.get(f"/api/documents/{private['id']}").status_code == 404
    listed = {item['id']: item for item in client.get('/api/folders').json()}
    assert set(listed) == {parent['id'], folder['id'], child['id']}
    assert not listed[parent['id']]['permissions']['read']
    assert listed[child['id']]['permissions']['read']
    loaded = client.get(f"/api/documents/{doc['id']}").json()
    update = {'title': 'Changed', 'version': loaded['version']}
    assert not loaded['permissions']['edit']
    assert client.put(f"/api/documents/{doc['id']}", json=update).status_code == 403
    assert client.post(f"/api/documents/{doc['id']}/comments", json={'content': 'Comment'}).status_code == 403
    assert client.patch(f"/api/documents/{doc['id']}/deadlines/{deadline['id']}", json={'done': True}).status_code == 403
    assert client.post(f"/api/documents/{doc['id']}/deadlines", json={'title': 'Due again', 'due_at': '2030-01-02T00:00:00+00:00'}).status_code == 403
    assert client.post(f"/api/documents/{doc['id']}/shares", json={'hours': 1}).status_code == 403
    assert client.patch(f"/api/folders/{child['id']}", json={'name': 'Renamed'}).status_code == (200 if right == 'can_edit' else 403)
    assert client.post('/api/folders', json={'name': 'New', 'parent_id': child['id']}).status_code == (201 if right == 'can_add' else 403)
    assert client.post('/api/files', data={'folder_id': child['id']}, files={'file': ('new.txt', b'new')}).status_code == (201 if right == 'can_add' else 403)
    assert client.delete(f"/api/documents/{doc['id']}").status_code == (204 if right == 'can_delete' else 403)
    assert client.delete(f"/api/folders/{child['id']}").status_code == (204 if right == 'can_delete' else 403)

def test_group_revocation_and_combined_grants(app_client):
    main, client = app_client
    reader = create_reader(client)
    parent, folder, child, doc, group = make_shared(client, reader, {'can_read': True})
    second = client.post('/api/admin/groups', json={'name': 'Editors'}).json()
    client.put(f"/api/admin/groups/{second['id']}/members/{reader['id']}")
    client.put(f"/api/admin/groups/{second['id']}/permissions", json={'folder_id': child['id'], 'can_edit': True, 'can_add': True})
    login(client, READER)
    assert not client.get(f"/api/documents/{doc['id']}").json()['permissions']['edit']
    own_doc = client.post('/api/documents', json={'title': 'Own document', 'folder_id': child['id']}).json()
    assert client.get(f"/api/documents/{own_doc['id']}").json()['permissions']['edit']
    assert client.put(f"/api/documents/{own_doc['id']}", json={'title': 'Edited', 'version': own_doc['version']}).status_code == 200
    login(client, ADMIN)
    client.delete(f"/api/admin/groups/{second['id']}")
    login(client, READER)
    assert not client.get(f"/api/documents/{doc['id']}").json()['permissions']['edit']
    assert not client.get(f"/api/documents/{own_doc['id']}").json()['permissions']['edit']
    login(client, ADMIN)
    client.delete(f"/api/admin/groups/{group['id']}/members/{reader['id']}")
    login(client, READER)
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404
    # The uploader still sees the path to their own document after revocation.
    assert {item['id'] for item in client.get('/api/folders').json()} == {parent['id'],folder['id'],child['id']}

def test_only_uploader_can_delete_or_replace_shared_files(app_client):
    main, client = app_client
    reader = create_reader(client)
    parent, folder, child, doc, group = make_shared(client, reader, {'can_read': True, 'can_add': True, 'can_edit': True, 'can_delete': True})
    login(client, READER)
    uploaded = client.post('/api/files', data={'folder_id': child['id'], 'uploaded_by': 'fake'}, files={'file': ('test.txt', b'test')}).json()
    assert uploaded['uploaded_by'] == reader['id']
    login(client, ADMIN)
    loaded = client.get(f"/api/documents/{uploaded['id']}").json()
    assert not loaded['permissions']['edit'] and not loaded['permissions']['delete']
    assert client.put(f"/api/documents/{uploaded['id']}", json={'title': 'Foreign edit', 'version': loaded['version']}).status_code == 403
    assert client.delete(f"/api/documents/{uploaded['id']}").status_code == 403
    assert client.post(f"/api/documents/{uploaded['id']}/file", files={'file': ('bad.txt', b'bad')}).status_code == 403
    login(client, READER)
    assert client.delete(f"/api/documents/{uploaded['id']}").status_code == 204

def test_root_grants_and_account_rights(app_client):
    main, client = app_client
    reader = create_reader(client)
    doc = client.post('/api/documents', json={'title': 'Root'}).json()
    group = client.post('/api/admin/groups', json={'name': 'Global'}).json()
    client.put(f"/api/admin/groups/{group['id']}/members/{reader['id']}")
    client.put(f"/api/admin/groups/{group['id']}/permissions", json={'can_read': True})
    login(client, READER)
    assert client.get(f"/api/documents/{doc['id']}").status_code == 200
    assert not client.get('/api/access').json()['add']
    login(client, ADMIN)
    assert client.patch(f"/api/admin/users/{reader['id']}", json={'can_add': True, 'can_delete': True}).status_code == 200
    login(client, READER)
    own_doc = client.post('/api/documents', json={'title': 'Own'}).json()
    assert client.delete(f"/api/documents/{own_doc['id']}").status_code == 204
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 403

def test_administrator_cannot_lock_self_out(app_client):
    main, client = app_client
    uid = client.get('/api/me').json()['id']
    assert client.patch(f'/api/admin/users/{uid}', json={'active': False}).status_code == 409
    assert client.patch(f'/api/admin/users/{uid}', json={'role': 'user'}).status_code == 409
    assert client.get('/api/me').json()['role'] == 'admin'

def test_password_reset_ends_sessions(app_client):
    main, client = app_client
    reader = create_reader(client)
    login(client, READER)
    old_cookie = client.cookies.get('session')
    assert client.post('/api/login', json=ADMIN).status_code == 200
    assert client.patch(f"/api/admin/users/{reader['id']}", json={'password': 'new-password-123'}).status_code == 200
    assert client.get('/api/me', headers={'cookie': f'session={old_cookie}'}).status_code == 401
    assert client.post('/api/login', json=READER).status_code == 401
    assert client.post('/api/login', json={'name': READER['name'], 'password': 'new-password-123'}).status_code == 200

def test_role_changes_apply_without_new_login(app_client):
    main, client = app_client
    reader = create_reader(client, role='admin')
    login(client, READER)
    cookie = client.cookies.get('session')
    assert client.get('/api/admin/users').status_code == 200
    assert client.post('/api/login', json=ADMIN).status_code == 200
    client.patch(f"/api/admin/users/{reader['id']}", json={'role': 'user'})
    assert client.get('/api/admin/users', headers={'cookie': f'session={cookie}'}).status_code == 403

def test_old_database_migration_preserves_files_and_promotes_first_account(app_client):
    main, client = app_client
    with main.db() as con:
        con.execute(f'DROP SCHEMA "{con.schema}" CASCADE')
        con.ensure_schema()
        con.execute('CREATE TABLE users(id TEXT PRIMARY KEY, name TEXT NOT NULL, password TEXT NOT NULL)')
        con.execute('INSERT INTO users VALUES(?,?,?)', ('legacy-owner', 'legacy', main.password_hash('legacy-password-123')))
        con.execute('CREATE TABLE documents(id TEXT PRIMARY KEY,user_id TEXT,title TEXT,category TEXT,content TEXT,status TEXT,created_at TEXT,updated_at TEXT,version INTEGER,filename TEXT,file BYTEA)')
        con.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?)', ('legacy-file','legacy-owner','file.txt','Pliki','','Gotowy',main.now(),main.now(),1,'file.txt',b'legacy'))
    main.initialize()
    main.initialize()
    login(client, {'name': 'legacy', 'password': 'legacy-password-123'})
    assert client.get('/api/me').json()['role'] == 'admin'
    assert client.get('/api/documents').json()[0]['uploaded_by'] == 'legacy-owner'
    assert client.get('/api/documents/legacy-file/file').content == b'legacy'


