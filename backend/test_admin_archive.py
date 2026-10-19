from fastapi.testclient import TestClient
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, create_account, login
from backend.test_companies import superadmin


def test_company_admin_can_read_private_document_and_file_without_editing(app_client):
    _, client = app_client
    account = create_reader(client, can_add=True)
    with TestClient(client.app) as customer:
        login(customer, READER)
        folder = customer.post('/api/folders', json={'name': 'Private', 'access_mode': 'private'}).json()
        doc = customer.post('/api/documents', json={'title': 'Private document', 'content': 'Keep content', 'folder_id': folder['id']}).json()
        file = customer.post('/api/files', data={'folder_id': folder['id']}, files={'file': ('original.txt', b'original bytes')}).json()
    assert client.get('/api/documents/' + doc['id']).status_code == 200
    assert client.get('/api/documents/' + file['id'] + '/file').content == b'original bytes'
    rights = client.get('/api/documents/' + doc['id']).json()['permissions']
    assert rights['read'] and not rights['edit']
    assert client.delete('/api/documents/' + doc['id']).status_code == 403
    assert client.delete('/api/admin/users/' + account['id']).status_code == 204
    assert client.get('/api/documents/' + doc['id']).json()['content'] == 'Keep content'
    assert client.get('/api/documents/' + file['id'] + '/file').content == b'original bytes'
    assert folder['id'] in {row['id'] for row in client.get('/api/folders').json()}


def test_admin_preview_active_or_blocked_accounts_is_read_only_and_returnable(app_client):
    _, client = app_client
    account = create_reader(client, can_add=True, can_edit=True)
    task = client.post('/api/tasks', json={'title': 'Preview task', 'assignee_id': account['id']}).json()
    for active in (True, False):
        assert client.patch('/api/admin/users/' + account['id'], json={'active': active}).status_code == 200
        start = client.post('/api/admin/users/' + account['id'] + '/impersonate')
        assert start.status_code == 200 and start.json()['read_only']
        assert client.get('/api/me').json()['impersonation']['read_only']
        preview_task = next(item for item in client.get('/api/tasks').json()['mine'] if item['id'] == task['id'])
        assert not preview_task['can_update'] and not preview_task['can_delete']
        assert client.post('/api/documents', json={'title': 'Forbidden'}).status_code == 403
        assert client.post('/api/admin/impersonation/stop').status_code == 200
        assert client.get('/api/me').json()['role'] == 'admin'


def test_preview_and_direct_read_respect_company_boundary(app_client):
    main, client = app_client
    superadmin(main)
    company = client.post('/api/admin/companies', json={'name': 'Foreign company'}).json()
    other = create_account(client, name='foreign-preview', password='foreign-preview-password', company_id=company['id'], can_add=True)
    own = create_reader(client, role='admin')
    login(client, {'name': 'foreign-preview', 'password': 'foreign-preview-password'})
    doc = client.post('/api/documents', json={'title': 'Other company document'}).json()
    login(client, READER)
    assert client.post('/api/admin/users/' + other['id'] + '/impersonate').status_code == 404
    assert client.get('/api/documents/' + doc['id']).status_code == 404
    assert other['id'] not in {row['id'] for row in client.get('/api/admin/users?include_deleted=true').json()}
    login(client, ADMIN)
    assert client.get('/api/documents/' + doc['id']).status_code == 200


def test_superadmin_keeps_existing_write_mode_for_active_account(app_client):
    main, client = app_client
    superadmin(main)
    account = create_reader(client, can_add=True)
    start = client.post('/api/admin/users/' + account['id'] + '/impersonate')
    assert start.status_code == 200 and start.json()['read_only'] is False
    assert client.post('/api/documents', json={'title': 'Existing write behavior'}).status_code == 201
    assert client.post('/api/admin/impersonation/stop').status_code == 200


def test_losing_admin_role_immediately_revokes_preview(app_client):
    main, client = app_client
    actor = client.get('/api/me').json()
    account = create_reader(client)
    assert client.post('/api/admin/users/' + account['id'] + '/impersonate').status_code == 200
    with main.db() as con:
        con.execute("UPDATE users SET role='user' WHERE id=?", (actor['id'],))
    assert client.get('/api/documents').status_code == 409
    me = client.get('/api/me').json()
    assert me['id'] == actor['id'] and 'impersonation' not in me
