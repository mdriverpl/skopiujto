import pytest

from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, create_account, login
from backend.test_mailing import smtp, upload, send


def test_assign_receive_start_complete_persist_and_sender_cannot_complete_for_recipient(app_client):
    main, client = app_client
    reader = create_reader(client)
    response = client.post('/api/tasks', json={'title': 'Podpisz umowę', 'kind': 'signature',
        'description': 'Sprawdź dane stron i podpisz dokument.', 'assignee_id': reader['id'], 'due_at': '2030-01-02T10:00:00+01:00'})
    assert response.status_code == 201, response.text
    item = response.json()
    assert item['status'] == 'todo' and item['due_at'] == '2030-01-02T09:00:00+00:00'
    listing = client.get('/api/tasks').json()
    assert listing['mine'] == [] and len(listing['sent']) == 1 and listing['waiting'] == 0
    assert client.patch('/api/tasks/' + item['id'] + '/status', json={'status': 'done', 'version': 1}).status_code == 403
    main.initialize()
    login(client, READER)
    listing = client.get('/api/tasks').json()
    assert listing['mine'][0]['title'] == 'Podpisz umowę' and listing['sent'] == [] and listing['waiting'] == 1
    started = client.patch('/api/tasks/' + item['id'] + '/status', json={'status': 'in_progress', 'version': 1})
    assert started.status_code == 200 and started.json()['version'] == 2
    assert client.patch('/api/tasks/' + item['id'] + '/status', json={'status': 'done', 'version': 1}).status_code == 409
    completed = client.patch('/api/tasks/' + item['id'] + '/status', json={'status': 'done', 'version': 2})
    assert completed.status_code == 200 and completed.json()['completed_at']
    assert client.get('/api/tasks').json()['waiting'] == 0
    login(client, ADMIN)
    assert client.get('/api/tasks').json()['sent'][0]['status'] == 'done'
    assert client.patch('/api/tasks/' + item['id'] + '/status', json={'status': 'cancelled', 'version': 3}).status_code == 409


def test_tasks_visible_only_to_participants_and_sender_only_cancels(app_client):
    _, client = app_client
    reader = create_reader(client)
    task = client.post('/api/tasks', json={'title': 'Zadanie', 'assignee_id': reader['id']}).json()
    third = create_account(client, **{'name': 'third', 'password': 'third-password-123', 'role': 'admin'})
    login(client, {'name': 'third', 'password': 'third-password-123'})
    assert client.get('/api/tasks').json() == {'mine': [], 'sent': [], 'waiting': 0}
    assert client.patch('/api/tasks/' + task['id'] + '/status', json={'status': 'done', 'version': 1}).status_code == 404
    login(client, READER)
    assert client.patch('/api/tasks/' + task['id'] + '/status', json={'status': 'cancelled', 'version': 1}).status_code == 403
    login(client, ADMIN)
    assert client.patch('/api/tasks/' + task['id'] + '/status', json={'status': 'cancelled', 'version': 1}).status_code == 200
    login(client, READER)
    assert client.get('/api/tasks').json()['waiting'] == 0
    assert client.patch('/api/tasks/' + task['id'] + '/status', json={'status': 'done', 'version': 2}).status_code == 409
    client.post('/api/logout')
    assert client.get('/api/tasks').status_code == 401
    assert client.post('/api/tasks', json={'title': 'x', 'assignee_id': reader['id']}).status_code == 401


def test_file_approvals_appear_in_both_task_filters_without_duplicates_or_new_email(app_client, smtp):
    _, client = app_client
    reader = create_reader(client)
    doc = upload(client)
    people = send(client, doc, [{'channel': 'user', 'user_id': reader['id']}, {'email': 'anna@example.com'}]).json()['history'][0]['recipients']
    sent = client.get('/api/tasks').json()['sent']
    assert len(sent) == 2 and {item['channel'] for item in sent} == {'user', 'email'}
    assert all(item['document_id'] == doc['id'] and item['origin'] == 'approval' for item in sent)
    assert len(smtp) == 1
    login(client, READER)
    mine = client.get('/api/tasks').json()
    assert len(mine['mine']) == 1 and mine['waiting'] == 1 and mine['mine'][0]['document_id'] is None
    assert mine['mine'][0]['can_download'] and mine['mine'][0]['can_accept']
    assert client.post('/api/approval-inbox/' + people[0]['id'] + '/accept', json={'confirmed': True}).status_code == 200
    assert client.get('/api/tasks').json()['mine'][0]['status'] == 'accepted'
    login(client, ADMIN)
    assert {item['status'] for item in client.get('/api/tasks').json()['sent']} == {'waiting', 'accepted'}


def test_document_tasks_use_existing_status_and_assigning_does_not_grant_access_or_edit(app_client):
    main, client = app_client
    reader = create_reader(client)
    private = client.post('/api/documents', json={'title': 'Private', 'status': 'Do podpisania'}).json()
    mine = client.get('/api/tasks').json()['mine']
    assert mine[0]['origin'] == 'document' and mine[0]['kind'] == 'signature' and mine[0]['document_id'] == private['id']
    assert client.post('/api/tasks', json={'title': 'Podpisz', 'kind': 'signature',
        'assignee_id': reader['id'], 'document_id': private['id']}).status_code == 422
    folder = client.post('/api/folders', json={'name': 'Shared', 'access_mode': 'users', 'user_ids': [reader['id']]}).json()
    shared = client.post('/api/documents', json={'title': 'Shared contract', 'folder_id': folder['id']}).json()
    body = {'title': 'Podpisz', 'kind': 'signature', 'assignee_id': reader['id'], 'document_id': shared['id']}
    task = client.post('/api/tasks', json=body)
    assert task.status_code == 201
    assert client.post('/api/tasks', json={**body, 'kind': 'modification'}).status_code == 422
    login(client, READER)
    assert client.get('/api/tasks').json()['mine'][0]['document_id'] == shared['id']
    assert client.post('/api/tasks', json={'title': 'Hidden', 'assignee_id': reader['id'], 'document_id': private['id']}).status_code == 404
    # Revoking folder access hides the document link, without losing the assigned task.
    with main.db() as con: con.execute('DELETE FROM folder_user_permissions WHERE user_id=?', (reader['id'],))
    assert client.get('/api/tasks').json()['mine'][0]['document_id'] is None
    login(client, ADMIN)
    assert client.delete('/api/documents/' + shared['id']).status_code == 204
    assert client.get('/api/tasks').json()['sent'][0]['document_id'] is None


@pytest.mark.parametrize('extra', [{'title': ' '}, {'title': 'x' * 201}, {'kind': 'invalid'},
    {'due_at': '2030-01-01T10:00:00'}, {'description': 'x' * 5001}, {'assignee_id': 'missing'}])
def test_invalid_task_does_not_create_records(app_client, extra):
    _, client = app_client
    reader = create_reader(client)
    assert client.post('/api/tasks', json={'title': 'Task', 'assignee_id': reader['id'], **extra}).status_code == 422
    assert client.get('/api/tasks').json()['sent'] == []


def test_self_assigned_task_and_inactive_recipient(app_client):
    _, client = app_client
    current = client.get('/api/me').json()
    response = client.post('/api/tasks', json={'title': 'Dla mnie', 'assignee_id': current['id']})
    assert response.status_code == 201
    listing = client.get('/api/tasks').json()
    assert listing['mine'][0]['id'] == listing['sent'][0]['id'] and listing['waiting'] == 1
    reader = create_reader(client)
    client.patch('/api/admin/users/' + reader['id'], json={'active': False})
    assert client.post('/api/tasks', json={'title': 'Task', 'assignee_id': reader['id']}).status_code == 422


def test_existing_document_deadline_is_a_task_and_completion_uses_existing_permissions(app_client):
    _, client = app_client
    document = client.post('/api/documents', json={'title': 'Umowa', 'status': 'Gotowy'}).json()
    deadline = client.post('/api/documents/' + document['id'] + '/deadlines', json={
        'title': 'Wyślij podpisany egzemplarz', 'due_at': '2030-01-01T12:00:00Z'}).json()['deadlines'][0]
    listing = client.get('/api/tasks').json()
    assert listing['waiting'] == 1 and listing['mine'][0]['origin'] == 'deadline'
    assert listing['mine'][0]['can_update']
    assert client.patch(f"/api/documents/{document['id']}/deadlines/{deadline['id']}", json={'done': True}).status_code == 200
    listing = client.get('/api/tasks').json()
    assert listing['waiting'] == 0 and listing['mine'][0]['status'] == 'done'


def test_folder_tasks_check_both_participants_access_and_hide_revoked_links(app_client):
    main, client = app_client
    reader = create_reader(client)
    private = client.post('/api/folders', json={'name': 'Private', 'access_mode': 'private'}).json()
    shared = client.post('/api/folders', json={'name': 'Contracts', 'access_mode': 'users', 'user_ids': [reader['id']]}).json()
    body = {'title': 'Uporządkuj katalog', 'assignee_id': reader['id'], 'folder_id': private['id']}
    assert client.post('/api/tasks', json=body).status_code == 422
    response = client.post('/api/tasks', json={**body, 'folder_id': shared['id']})
    assert response.status_code == 201
    assert response.json()['folder_name'] == 'Contracts' and response.json()['document_id'] is None
    main.initialize()
    login(client, READER)
    item = client.get('/api/tasks').json()['mine'][0]
    assert item['folder_id'] == shared['id'] and item['folder_name'] == 'Contracts'
    assert client.post('/api/tasks', json=body).status_code == 404
    with main.db() as con: con.execute('DELETE FROM folder_user_permissions WHERE user_id=?', (reader['id'],))
    item = client.get('/api/tasks').json()['mine'][0]
    assert item['folder_id'] is None and item['folder_name'] is None
    login(client, ADMIN)
    assert client.delete('/api/folders/' + shared['id']).status_code == 204
    item = client.get('/api/tasks').json()['sent'][0]
    assert item['folder_id'] is None and item['title'] == body['title']


def test_task_resource_validation_and_general_task(app_client):
    _, client = app_client
    me = client.get('/api/me').json()
    folder = client.post('/api/folders', json={'name': 'Work'}).json()
    document = client.post('/api/documents', json={'title': 'Contract'}).json()
    body = {'title': 'Review', 'assignee_id': me['id']}
    assert client.post('/api/tasks', json={**body, 'folder_id': folder['id'], 'document_id': document['id']}).status_code == 422
    assert client.post('/api/tasks', json={**body, 'folder_id': ''}).status_code == 422
    assert client.post('/api/tasks', json={**body, 'folder_id': 'missing'}).status_code == 404
    item = client.post('/api/tasks', json=body).json()
    assert item['folder_id'] is None and item['document_id'] is None


def test_legacy_task_schema_migrates_without_losing_tasks(postgres_schema):
    from backend import tasks, database
    with database.connect(postgres_schema) as con:
        con.execute('CREATE TABLE users(id TEXT PRIMARY KEY)')
        con.execute('CREATE TABLE documents(id TEXT PRIMARY KEY)')
        con.execute('CREATE TABLE folders(id TEXT PRIMARY KEY)')
        con.execute("INSERT INTO users VALUES('me')")
        con.executescript(tasks.SCHEMA.replace('folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL, ', ''))
        con.execute("INSERT INTO user_tasks(id,sender_id,assignee_id,title,description,kind,created_at,updated_at) VALUES('task','me','me','Legacy','','general','date','date')")
        tasks.initialize(con)
        tasks.initialize(con)
        row = con.execute('SELECT * FROM user_tasks').fetchone()
        assert row['id'] == 'task' and row['folder_id'] is None
