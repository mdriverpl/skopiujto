import io
import pytest
from PIL import Image
from backend import audit
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login

def history(client, kind, identifier):
    response = client.get(f'/api/history/{kind}/{identifier}')
    assert response.status_code == 200, response.text
    return response.json()['items']

def test_document_changes_snapshot_user_and_before_after_without_false_entries(app_client):
    main, client = app_client
    doc = client.post('/api/documents', json={'title': 'Umowa', 'content': 'Stara treść'}).json()
    assert history(client, 'document', doc['id'])[0]['action'] == 'Utworzono dokument'
    changed = client.put('/api/documents/' + doc['id'], json={'title': 'Nowa nazwa', 'content': 'Nowa treść', 'version': doc['version']})
    assert changed.status_code == 200
    entries = history(client, 'document', doc['id'])
    assert len(entries) == 2 and entries[0]['actor_name'] == ADMIN['name'] and entries[0]['created_at']
    values = {item['field']: item for item in entries[0]['changes']}
    assert values['title']['before'] == 'Umowa' and values['title']['after'] == 'Nowa nazwa'
    assert values['content']['before'] == 'Stara treść' and values['content']['after'] == 'Nowa treść'
    assert client.put('/api/documents/' + doc['id'], json={'title': 'Bad', 'content': '', 'version': doc['version']}).status_code == 409
    assert len(history(client, 'document', doc['id'])) == 2
    current = changed.json()
    assert client.put('/api/documents/' + doc['id'], json={'title': current['title'], 'content': current['content'], 'category': current['category'], 'status': current['status'], 'version': current['version']}).status_code == 200
    assert len(history(client, 'document', doc['id'])) == 2
    main.initialize()
    assert len(history(client, 'document', doc['id'])) == 2

def test_history_obeys_resource_acl_and_retains_deleted_owner_entries(app_client):
    _, client = app_client
    reader = create_reader(client)
    doc = client.post('/api/documents', json={'title': 'Prywatny'}).json()
    login(client, READER)
    assert client.get('/api/history/document/' + doc['id']).status_code == 404
    assert client.put('/api/documents/' + doc['id'], json={'title': 'Hack', 'content': '', 'version': doc['version']}).status_code == 404
    login(client, ADMIN)
    assert len(history(client, 'document', doc['id'])) == 1
    assert client.delete('/api/documents/' + doc['id']).status_code == 204
    assert history(client, 'document', doc['id'])[0]['action'] == 'Usunięto'
    login(client, READER)
    assert client.get('/api/history/document/' + doc['id']).status_code == 404
    client.post('/api/logout')
    assert client.get('/api/history/document/' + doc['id']).status_code == 401

def test_template_updates_and_deletion_keep_diff_and_private_access(app_client):
    _, client = app_client
    create_reader(client)
    template = client.post('/api/templates', json={'title': 'Wzór', 'content': 'Pierwsza treść'}).json()
    result = client.put('/api/templates/' + template['id'], json={'title': 'Wzór', 'content': 'Druga treść', 'description': 'Opis', 'version': template['version']})
    assert result.status_code == 200
    entries = history(client, 'template', template['id'])
    assert any(change['field'] == 'content' and change['after'] == 'Druga treść' for change in entries[0]['changes'])
    login(client, READER)
    assert client.get('/api/history/template/' + template['id']).status_code == 404
    login(client, ADMIN)
    assert client.delete('/api/templates/' + template['id']).status_code == 204
    assert history(client, 'template', template['id'])[0]['action'] == 'Usunięto'

def test_folder_renames_shared_actor_permissions_and_failed_rename(app_client):
    _, client = app_client
    reader = create_reader(client)
    folder = client.post('/api/folders', json={'name': 'Folder', 'access_mode': 'users', 'user_ids': [reader['id']], 'can_edit': True}).json()
    login(client, READER)
    assert client.patch('/api/folders/' + folder['id'], json={'name': 'Nowy folder'}).status_code == 200
    entry = history(client, 'folder', folder['id'])[0]
    assert entry['actor_id'] == reader['id'] and entry['actor_name'] == 'reader'
    assert entry['changes'][0]['before'] == 'Folder' and entry['changes'][0]['after'] == 'Nowy folder'
    login(client, ADMIN)
    client.post('/api/folders', json={'name': 'Istniejący'})
    assert client.patch('/api/folders/' + folder['id'], json={'name': 'Istniejący'}).status_code == 409
    assert len(history(client, 'folder', folder['id'])) == 2
    group = client.post('/api/admin/groups', json={'name': 'Grupa'}).json()
    assert client.put('/api/admin/groups/' + group['id'] + '/permissions', json={'folder_id': folder['id'], 'can_read': True}).status_code == 200
    assert history(client, 'folder', folder['id'])[0]['action'] == 'Zmieniono uprawnienia grupy'
    client.delete('/api/folders/' + folder['id'])
    assert history(client, 'folder', folder['id'])[0]['action'] == 'Usunięto'

def test_files_replacement_and_image_crop_log_parameters(app_client):
    _, client = app_client
    file = client.post('/api/files', files={'file': ('one.txt', b'one')}).json()
    assert history(client, 'document', file['id'])[0]['action'] == 'Dodano plik'
    assert client.post('/api/documents/' + file['id'] + '/file', files={'file': ('two.txt', b'two two')}).status_code == 200
    entry = history(client, 'document', file['id'])[0]
    assert entry['action'] == 'Zastąpiono plik'
    assert entry['changes'][0]['before'] == 'one.txt' and entry['changes'][0]['after'] == 'two.txt'
    data = io.BytesIO(); Image.new('RGB', (20, 20), 'red').save(data, 'PNG')
    image = client.post('/api/files', files={'file': ('image.png', data.getvalue())}).json()
    result = client.post('/api/documents/' + image['id'] + '/image', json={'version': image['version'], 'x': 0, 'y': 0, 'width': 10, 'height': 10, 'output_width': 5, 'output_height': 5})
    assert result.status_code == 200, result.text
    entry = history(client, 'document', image['id'])[0]
    assert entry['action'] == 'Edytowano obraz' and 'output_width' in entry['changes'][0]['after']
    assert 'object_key' not in str(entry) and 'token_hash' not in str(entry)

def test_workflow_comments_deadlines_and_links_are_logged_without_tokens(app_client):
    _, client = app_client
    doc = client.post('/api/documents', json={'title': 'Umowa'}).json()
    result = client.patch('/api/documents/' + doc['id'] + '/status', json={'version': doc['version'], 'status': 'Do podpisania'})
    assert result.status_code == 200
    assert history(client, 'document', doc['id'])[0]['changes'][0]['field'] == 'status'
    client.post('/api/documents/' + doc['id'] + '/comments', json={'content': 'Komentarz'})
    result = client.post('/api/documents/' + doc['id'] + '/deadlines', json={'title': 'Termin', 'due_at': '2030-01-01T12:00:00Z'})
    deadline = result.json()['deadlines'][0]
    assert client.patch(f"/api/documents/{doc['id']}/deadlines/{deadline['id']}", json={'done': True}).status_code == 200
    share = client.post('/api/documents/' + doc['id'] + '/shares', json={'hours': 24}).json()
    entries = history(client, 'document', doc['id'])
    assert share['path'].split('/')[-1] not in str(entries)
    actions = {entry['action'] for entry in entries}
    assert {'Dodano komentarz', 'Dodano termin', 'Zmieniono termin', 'Utworzono link udostępnienia'} <= actions

def test_pagination_and_changed_excerpt_in_long_content(app_client):
    main, client = app_client
    doc = client.post('/api/documents', json={'title': 'History'}).json()
    current = client.get('/api/me').json()
    with main.db() as con:
        for index in range(105): audit.record(con, current, 'document', {'id': doc['id'], 'user_id': current['id'], 'title': doc['title']}, str(index))
    first = client.get('/api/history/document/' + doc['id']).json()
    second = client.get('/api/history/document/' + doc['id'], params={'before': first['next_before']}).json()
    assert len(first['items']) == 100 and len(second['items']) == 6
    assert not {r['id'] for r in first['items']} & {r['id'] for r in second['items']}
    diff = audit.differences({'content': 'x' * 10000 + 'Old'}, {'content': 'x' * 10000 + 'New'}, ['content'])
    assert 'Old' in diff[0]['before'] and 'New' in diff[0]['after']
    fields = audit.differences({'field_values': '{"Miasto":"Warszawa"}'}, {'field_values': '{"Miasto":"Kraków"}'}, ['field_values'])
    assert fields[0]['label'] == 'Dane dokumentu: Miasto' and fields[0]['before'] == 'Warszawa' and fields[0]['after'] == 'Kraków'

@pytest.mark.parametrize('uploaded', [True, False])
def test_deleted_file_is_logged_in_its_direct_folder_and_survives_restart(app_client, uploaded):
    main, client = app_client
    parent = client.post('/api/folders', json={'name': 'Parent'}).json()
    folder = client.post('/api/folders', json={'name': 'Child', 'parent_id': parent['id']}).json()
    if uploaded:
        doc = client.post('/api/files', data={'folder_id': folder['id']}, files={'file': ('deleted.txt', b'private content')}).json()
    else:
        doc = client.post('/api/documents', json={'title': 'Document', 'folder_id': folder['id']}).json()
    assert client.delete('/api/documents/' + doc['id']).status_code == 204
    entry = history(client, 'folder', folder['id'])[0]
    assert entry['action'] == ('Usunięto plik: deleted.txt' if uploaded else 'Usunięto dokument: Document')
    assert entry['actor_name'] == ADMIN['name'] and entry['created_at']
    details = {change['field']: change for change in entry['changes']}
    assert details['document_id']['before'] == doc['id']
    assert details['title']['before'] == doc['title']
    assert all(change['after'] is None for change in entry['changes'])
    assert 'private content' not in str(entry)
    assert len(history(client, 'folder', parent['id'])) == 1
    assert history(client, 'document', doc['id'])[0]['action'] == 'Usunięto'
    assert client.delete('/api/documents/' + doc['id']).status_code == 404
    assert len(history(client, 'folder', folder['id'])) == 2
    main.initialize()
    assert history(client, 'folder', folder['id'])[0]['id'] == entry['id']

def test_shared_folder_logs_file_uploader_and_rejected_deletion_does_not_log(app_client):
    _, client = app_client
    reader = create_reader(client)
    folder = client.post('/api/folders', json={'name': 'Shared', 'access_mode': 'users', 'user_ids': [reader['id']], 'can_add': True, 'can_delete': True}).json()
    login(client, READER)
    doc = client.post('/api/files', data={'folder_id': folder['id']}, files={'file': ('reader.txt', b'content')}).json()
    login(client, ADMIN)
    assert client.delete('/api/documents/' + doc['id']).status_code == 403
    assert len(history(client, 'folder', folder['id'])) == 1
    login(client, READER)
    assert client.delete('/api/documents/' + doc['id']).status_code == 204
    login(client, ADMIN)
    entry = history(client, 'folder', folder['id'])[0]
    assert entry['actor_id'] == reader['id'] and entry['actor_name'] == READER['name']
    assert entry['action'] == 'Usunięto plik: reader.txt'

def test_storage_failure_does_not_log_folder_deletion(app_client, monkeypatch):
    from fastapi import HTTPException
    main, client = app_client
    folder = client.post('/api/folders', json={'name': 'Folder'}).json()
    doc = client.post('/api/files', data={'folder_id': folder['id']}, files={'file': ('kept.txt', b'content')}).json()
    def fail(*args):
        raise HTTPException(503, 'Storage unavailable')
    monkeypatch.setattr(main.storage, 'delete', fail)
    assert client.delete('/api/documents/' + doc['id']).status_code == 503
    assert len(history(client, 'folder', folder['id'])) == 1
    assert len(history(client, 'document', doc['id'])) == 1
    assert client.get('/api/documents/' + doc['id']).status_code == 200
