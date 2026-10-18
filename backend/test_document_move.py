from backend.test_access import ADMIN, READER, create_reader, login
from backend.test_storage import app_client


def test_move_file_between_folders_and_root_preserves_attachment(app_client):
    main, client = app_client
    folder = client.post('/api/folders', json={'name': 'Docelowy', 'access_mode': 'private'}).json()
    doc = client.post('/api/files', files={'file': ('photo.png', b'original')}).json()
    assert doc['permissions']['move'] and not doc['permissions']['edit']
    response = client.patch(f"/api/documents/{doc['id']}/move", json={'folder_id': folder['id'], 'version': doc['version']})
    assert response.status_code == 200, response.text
    moved = response.json()
    assert moved['folder_id'] == folder['id']
    assert moved['version'] == doc['version']
    assert client.get(f"/api/documents/{doc['id']}/file").content == b'original'
    with main.db() as c:
        assert c.execute("SELECT count(*) FROM resource_history WHERE resource_id=? AND action='Przeniesiono dokument'", (doc['id'],)).fetchone()[0] == 1
    response = client.patch(f"/api/documents/{doc['id']}/move", json={'folder_id': None, 'version': moved['version']})
    assert response.status_code == 200
    assert response.json()['folder_id'] is None


def test_move_checks_version_destination_and_source_permissions(app_client):
    _, client = app_client
    reader = create_reader(client, can_add=True, can_delete=True)
    folder = client.post('/api/folders', json={'name': 'Wspólny', 'access_mode': 'users', 'user_ids': [reader['id']], 'can_add': True, 'can_delete': True}).json()
    private = client.post('/api/folders', json={'name': 'Prywatny', 'access_mode': 'private'}).json()
    doc = client.post('/api/documents', json={'title': 'Umowa', 'folder_id': folder['id']}).json()
    path = f"/api/documents/{doc['id']}/move"
    assert client.patch(path, json={'folder_id': None, 'version': doc['version'] + 1}).status_code == 409
    assert client.patch(path, json={'folder_id': 'missing', 'version': doc['version']}).status_code == 404
    login(client, READER)
    assert client.patch(path, json={'folder_id': None, 'version': doc['version']}).status_code == 403
    own = client.post('/api/documents', json={'title': 'Własny'}).json()
    assert client.patch(f"/api/documents/{own['id']}/move", json={'folder_id': private['id'], 'version': own['version']}).status_code == 404
    login(client, ADMIN)
    client.patch(f"/api/admin/users/{reader['id']}", json={'can_delete': False})
    login(client, READER)
    assert client.patch(f"/api/documents/{own['id']}/move", json={'folder_id': folder['id'], 'version': own['version']}).status_code == 403
