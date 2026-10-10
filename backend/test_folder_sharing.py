import pytest
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, create_account, login

def test_private_folder_excludes_root_and_parent_access(app_client):
    main, client = app_client
    reader = create_reader(client)
    group = client.post('/api/admin/groups', json={'name': 'Everyone'}).json()
    client.put(f"/api/admin/groups/{group['id']}/members/{reader['id']}")
    client.put(f"/api/admin/groups/{group['id']}/permissions", json={'can_read': True, 'can_add': True, 'can_edit': True, 'can_delete': True})
    parent = client.post('/api/folders', json={'name': 'Shared parent'}).json()
    private = client.post('/api/folders', json={'name': 'Private', 'parent_id': parent['id'], 'access_mode': 'private'}).json()
    uploaded = client.post('/api/files', data={'folder_id': private['id']}, files={'file': ('private.txt', b'private')}).json()
    login(client, READER)
    assert private['id'] not in {folder['id'] for folder in client.get('/api/folders').json()}
    assert parent['id'] in {folder['id'] for folder in client.get('/api/folders').json()}
    assert client.get(f"/api/documents/{uploaded['id']}").status_code == 404
    assert client.get(f"/api/documents/{uploaded['id']}/file").status_code == 404
    assert client.post('/api/files', data={'folder_id': private['id']}, files={'file': ('bad.txt', b'bad')}).status_code == 404
    assert client.patch(f"/api/folders/{private['id']}", json={'name': 'Bad'}).status_code == 404

@pytest.mark.parametrize('mode', ['users', 'groups'])
def test_selected_recipients_receive_only_chosen_permissions(app_client, mode):
    main, client = app_client
    reader = create_reader(client)
    group = client.post('/api/admin/groups', json={'name': 'Chosen group'}).json()
    client.put(f"/api/admin/groups/{group['id']}/members/{reader['id']}")
    recipients = {'user_ids': [reader['id']]} if mode == 'users' else {'group_ids': [group['id']]}
    response = client.post('/api/folders', json={'name': 'Selected', 'access_mode': mode, 'can_add': True, 'can_edit': False, 'can_delete': False, **recipients})
    assert response.status_code == 201
    folder = response.json()
    admin_file = client.post('/api/files', data={'folder_id': folder['id']}, files={'file': ('read.txt', b'read')}).json()
    private = client.post('/api/documents', json={'title': 'Outside'}).json()
    if mode == 'groups':
        group_info = client.get('/api/admin/groups').json()[0]
        assert group_info['permissions'][0]['folder_id'] == folder['id']
    login(client, READER)
    visible = {item['id']: item for item in client.get('/api/folders').json()}
    assert visible[folder['id']]['permissions'] == {'read': True, 'edit': False, 'add': True, 'delete': False}
    assert client.get(f"/api/documents/{admin_file['id']}/file").content == b'read'
    assert client.get(f"/api/documents/{private['id']}").status_code == 404
    assert client.patch(f"/api/folders/{folder['id']}", json={'name': 'Bad'}).status_code == 403
    assert client.delete(f"/api/documents/{admin_file['id']}").status_code == 403
    own_file = client.post('/api/files', data={'folder_id': folder['id']}, files={'file': ('own.txt', b'own')})
    assert own_file.status_code == 201
    assert client.put(f"/api/documents/{own_file.json()['id']}", json={'title': 'Bad', 'version': 1}).status_code == 403
    assert client.delete(f"/api/documents/{own_file.json()['id']}").status_code == 403

def test_user_sharing_inherits_but_private_child_cuts_it_off(app_client):
    main, client = app_client
    reader = create_reader(client)
    shared = client.post('/api/folders', json={'name': 'Shared', 'access_mode': 'users', 'user_ids': [reader['id']], 'can_add': True, 'can_edit': True, 'can_delete': True}).json()
    child = client.post('/api/folders', json={'name': 'Inherited', 'parent_id': shared['id']}).json()
    private = client.post('/api/folders', json={'name': 'Hidden child', 'parent_id': shared['id'], 'access_mode': 'private'}).json()
    login(client, READER)
    listed = {item['id']: item for item in client.get('/api/folders').json()}
    assert child['id'] in listed and private['id'] not in listed
    assert listed[child['id']]['permissions']['add'] and listed[child['id']]['permissions']['edit']
    doc = client.post('/api/documents', json={'title': 'Mine', 'folder_id': child['id']}).json()
    assert client.put(f"/api/documents/{doc['id']}", json={'title': 'Edited', 'version': doc['version']}).status_code == 200
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204

def test_unselected_user_has_no_access_even_with_root_grant(app_client):
    main, client = app_client
    reader = create_reader(client)
    outsider = create_account(client, **{'name': 'outsider', 'password': 'outsider-password-123'})
    broad = client.post('/api/admin/groups', json={'name': 'Root group'}).json()
    client.put(f"/api/admin/groups/{broad['id']}/members/{outsider['id']}")
    client.put(f"/api/admin/groups/{broad['id']}/permissions", json={'can_read': True})
    shared = client.post('/api/folders', json={'name': 'Selected only', 'access_mode': 'users', 'user_ids': [reader['id']]}).json()
    login(client, {'name': 'outsider', 'password': 'outsider-password-123'})
    assert shared['id'] not in {item['id'] for item in client.get('/api/folders').json()}

def test_invalid_recipients_do_not_create_folder(app_client):
    main, client = app_client
    reader = create_reader(client)
    owner_id = client.get('/api/me').json()['id']
    client.patch(f"/api/admin/users/{reader['id']}", json={'active': False})
    bodies = [
        {'access_mode': 'groups'}, {'access_mode': 'users'},
        {'access_mode': 'groups', 'group_ids': ['missing']},
        {'access_mode': 'users', 'user_ids': ['missing']},
        {'access_mode': 'users', 'user_ids': [reader['id']]},
        {'access_mode': 'users', 'user_ids': [owner_id]},
        {'access_mode': 'private', 'user_ids': [reader['id']]},
        {'access_mode': 'groups', 'group_ids': ['missing'], 'user_ids': [reader['id']]},
    ]
    for body in bodies:
        assert client.post('/api/folders', json={'name': 'Invalid', **body}).status_code == 422
    assert client.get('/api/folders').json() == []

def test_regular_creator_can_share_without_admin_access(app_client):
    main, client = app_client
    reader = create_reader(client, can_add=True)
    target = create_account(client, **{'name': 'target', 'password': 'target-password-123'})
    login(client, READER)
    choices = client.get('/api/sharing-options')
    assert choices.status_code == 200
    assert {'id': target['id'], 'name': 'target'} in choices.json()['users']
    assert all(set(item) == {'id', 'name'} for item in choices.json()['users'])
    assert client.get('/api/admin/users').status_code == 403
    response = client.post('/api/folders', json={'name': 'My shared folder', 'access_mode': 'users', 'user_ids': [target['id']], 'can_add': True})
    assert response.status_code == 201
    assert client.post('/api/folders', json={'name': 'Cannot delegate edit', 'access_mode': 'users', 'user_ids': [target['id']], 'can_edit': True}).status_code == 403
    private = client.post('/api/folders', json={'name': 'Mine', 'access_mode': 'private'}).json()
    assert client.post('/api/files', data={'folder_id': private['id']}, files={'file': ('mine.txt', b'mine')}).status_code == 201

def test_admin_can_revoke_group_access_created_with_folder(app_client):
    main, client = app_client
    reader = create_reader(client)
    group = client.post('/api/admin/groups', json={'name': 'Team'}).json()
    client.put(f"/api/admin/groups/{group['id']}/members/{reader['id']}")
    folder = client.post('/api/folders', json={'name': 'Group folder', 'access_mode': 'groups', 'group_ids': [group['id']]}).json()
    login(client, READER)
    assert folder['id'] in {item['id'] for item in client.get('/api/folders').json()}
    login(client, ADMIN)
    client.put(f"/api/admin/groups/{group['id']}/permissions", json={'folder_id': folder['id'], 'can_read': False, 'can_add': False, 'can_delete': False, 'can_edit': False})
    login(client, READER)
    assert folder['id'] not in {item['id'] for item in client.get('/api/folders').json()}
