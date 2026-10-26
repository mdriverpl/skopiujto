import io
import time
import zipfile

import pytest
from PIL import Image
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login
from backend.test_folder_archive import folder, upload


def create_link(client, kind, row, mode='catalog'):
    response = client.post(f"/api/external-links/{kind}/{row['id']}", json={'view_mode': mode, 'hours': 168})
    assert response.status_code == 201, response.text
    link = response.json()
    return link, '/api/public-shares/' + link['path'].rsplit('/', 1)[1]


def test_folder_link_public_navigation_download_scope_and_zip(app_client):
    main, client = app_client
    reader = create_reader(client)
    root = folder(client, 'Dokumenty', access_mode='users', user_ids=[reader['id']], can_add=True, can_edit=True)
    child = folder(client, 'Umowy', root['id'])
    own = upload(client, root, 'one.txt', b'one')
    nested = upload(client, child, 'two.txt', b'two')
    outside = upload(client, folder(client, 'Outside'), 'outside.txt', b'outside')
    link, url = create_link(client, 'folder', root, 'gallery')
    with main.db() as con:
        row = con.execute('SELECT * FROM external_links WHERE id=?', (link['id'],)).fetchone()
        assert link['path'].rsplit('/', 1)[1] not in row.values()
    login(client, READER)
    foreign = upload(client, root, 'foreign.txt', b'not shared by its author')
    assert client.post(f"/api/external-links/folder/{root['id']}", json={}).status_code == 404
    assert client.get(f"/api/external-links/folder/{root['id']}").status_code == 404
    assert client.delete('/api/external-links/' + link['id']).status_code == 404
    client.post('/api/logout')
    result = client.get(url)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['view_mode'] == 'gallery' and data['kind'] == 'folder'
    assert [row['id'] for row in data['files']] == [own['id']]
    assert data['folders'] == [{'id': child['id'], 'name': child['name']}]
    descendant = client.get(url, params={'folder_id': child['id']}).json()
    assert descendant['files'][0]['id'] == nested['id']
    assert len(descendant['breadcrumbs']) == 2
    for row in (outside, foreign):
        for suffix in ('', '/file', '/preview'):
            assert client.get(url + '/documents/' + row['id'] + suffix).status_code == 404
    assert client.get(url, params={'folder_id': outside['folder_id']}).status_code == 404
    assert client.get(url + '/documents/' + nested['id'] + '/file').content == b'two'
    result = client.get(url + '/archive')
    assert result.status_code == 200, result.text
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert 'Dokumenty/one.txt' in archive.namelist()
        assert 'Dokumenty/Umowy/two.txt' in archive.namelist()
        assert not any('foreign' in name or 'outside' in name for name in archive.namelist())
    login(client, ADMIN)
    response = client.patch('/api/external-links/' + link['id'], json={'view_mode': 'tiles'})
    assert response.status_code == 200
    assert client.get(url).json()['view_mode'] == 'tiles'
    moved = client.patch('/api/documents/' + nested['id'] + '/move', json={'version': nested['version'], 'folder_id': None})
    assert moved.status_code == 200, moved.text
    assert client.get(url + '/documents/' + nested['id'] + '/file').status_code == 404


def test_image_sharing_is_available_without_image_edit_permission_and_exposes_no_private_fields(app_client):
    _, client = app_client
    output = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(output, 'PNG')
    row = upload(client, folder(client, 'Images'), 'photo.png', output.getvalue())
    assert not row['permissions']['edit'] and row['can_share']
    link, url = create_link(client, 'document', row, 'preview')
    client.post('/api/logout')
    data = client.get(url).json()
    assert data['kind'] == 'document' and data['document']['image']
    assert 'user_id' not in data['document']
    details = client.get(url + '/documents/' + row['id']).json()
    assert not {'user_id', 'object_key', 'object_bucket', 'file', 'field_values', 'shares'} & details.keys()
    preview = client.get(url + '/documents/' + row['id'] + '/preview')
    assert preview.status_code == 200 and preview.headers['content-type'] == 'image/png'
    assert preview.content == output.getvalue()
    assert client.get(url + '/documents/' + row['id'] + '/file').content == output.getvalue()


@pytest.mark.parametrize('change', ['revoke', 'expire', 'deactivate', 'permissions'])
def test_public_link_lifecycle_blocks_all_content_endpoints(app_client, change):
    main, client = app_client
    root = folder(client, 'Shared')
    row = upload(client, root, 'secret.txt', b'content')
    link, url = create_link(client, 'folder', root)
    if change == 'revoke':
        assert client.delete('/api/external-links/' + link['id']).status_code == 204
    else:
        with main.db() as con:
            if change == 'expire': con.execute('UPDATE external_links SET expires=? WHERE id=?', (time.time() - 1, link['id']))
            elif change == 'deactivate': con.execute('UPDATE users SET active=0 WHERE id=?', (root['user_id'],))
            else: con.execute('UPDATE users SET can_edit=0 WHERE id=?', (root['user_id'],))
    client.post('/api/logout')
    for suffix in ('', '/archive', '/documents/' + row['id'], '/documents/' + row['id'] + '/file', '/documents/' + row['id'] + '/preview'):
        assert client.get(url + suffix).status_code in (404, 410)


def test_editor_document_has_public_preview_pdf_and_validated_link_modes(app_client):
    _, client = app_client
    root = folder(client, 'Documents')
    row = client.post('/api/documents', json={'title': 'Note', 'content': 'Hello', 'folder_id': root['id']}).json()
    assert client.post(f"/api/external-links/folder/{root['id']}", json={'view_mode': 'preview'}).status_code == 422
    assert client.post(f"/api/external-links/document/{row['id']}", json={'view_mode': 'invalid'}).status_code == 422
    assert client.post(f"/api/external-links/document/{row['id']}", json={'hours': 0}).status_code == 422
    link, url = create_link(client, 'document', row, 'preview')
    client.post('/api/logout')
    assert client.get(url + '/documents/' + row['id']).json()['content'] == 'Hello'
    assert client.get(url + '/documents/' + row['id'] + '/file').content.startswith(b'%PDF-')
    assert client.get(url + '/documents/' + row['id'] + '/preview').headers['content-type'] == 'application/pdf'
    assert client.get('/api/public-shares/not-a-token').status_code == 404
