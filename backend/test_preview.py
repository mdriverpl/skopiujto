import io

import pytest
from botocore.response import StreamingBody
from botocore.stub import ANY
from backend.test_storage import app_client, s3, put_params
from backend.test_access import ADMIN, READER, create_reader, login

@pytest.mark.parametrize('filename,mime', [('image.PNG', 'image/png'), ('photo.jpg', 'image/jpeg'), ('photo.jpeg', 'image/jpeg'), ('image.webp', 'image/webp'), ('image.gif', 'image/gif'), ('image.avif', 'image/avif'), ('image.svg', 'image/svg+xml')])
def test_image_preview_and_download_headers(app_client, filename, mime):
    main, client = app_client
    uploaded = client.post('/api/files', files={'file': (filename, b'image-bytes')}).json()
    response = client.get(f"/api/documents/{uploaded['id']}/preview")
    assert response.status_code == 200 and response.content == b'image-bytes'
    assert response.headers['content-type'].split(';')[0] == mime
    assert response.headers['content-disposition'].startswith('inline;')
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert "sandbox" in response.headers['content-security-policy']
    download = client.get(f"/api/documents/{uploaded['id']}/file")
    assert download.headers['content-disposition'].startswith('attachment;')

def test_preview_enforces_private_folder_and_session(app_client):
    main, client = app_client
    reader = create_reader(client)
    folder = client.post('/api/folders', json={'name': 'Private', 'access_mode': 'private'}).json()
    doc = client.post('/api/files', data={'folder_id': folder['id']}, files={'file': ('image.png', b'image')}).json()
    client.post('/api/logout')
    assert client.get(f"/api/documents/{doc['id']}/preview").status_code == 401
    login(client, READER)
    assert client.get(f"/api/documents/{doc['id']}/preview").status_code == 404

def test_preview_allows_shared_read_only_access(app_client):
    main, client = app_client
    reader = create_reader(client)
    folder = client.post('/api/folders', json={'name': 'Images', 'access_mode': 'users', 'user_ids': [reader['id']]}).json()
    doc = client.post('/api/files', data={'folder_id': folder['id']}, files={'file': ('image.png', b'image')}).json()
    login(client, READER)
    response = client.get(f"/api/documents/{doc['id']}/preview")
    assert response.status_code == 200 and response.content == b'image'

def test_preview_rejects_unsupported_files_and_missing_attachment(app_client):
    main, client = app_client
    uploaded = client.post('/api/files', files={'file': ('page.html', b'<html>test</html>')}).json()
    assert client.get(f"/api/documents/{uploaded['id']}/preview").status_code == 415
    text = client.post('/api/documents', json={'title': 'Text'}).json()
    assert client.get(f"/api/documents/{text['id']}/preview").status_code == 404

def test_s3_image_preview(s3):
    main, client, stub = s3
    stub.add_response('put_object', {}, put_params(b'image'))
    doc = client.post('/api/files', files={'file': ('image.png', b'image')}).json()
    stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(b'image'), 5)}, {'Bucket': 'private-test-bucket', 'Key': ANY})
    response = client.get(f"/api/documents/{doc['id']}/preview")
    assert response.status_code == 200 and response.content == b'image'
    assert response.headers['content-type'] == 'image/png'

@pytest.mark.parametrize('filename', ['photo.PNG', 'drawing.svg', 'photo.heic'])
def test_graphic_file_editing_is_disabled_for_author(app_client, filename):
    main, client = app_client
    doc = client.post('/api/files', files={'file': (filename, b'image')}).json()
    assert doc['permissions']['read'] and doc['permissions']['delete']
    assert not doc['permissions']['edit']
    assert not client.get('/api/documents').json()[0]['permissions']['edit']
    assert client.put(f"/api/documents/{doc['id']}", json={'title': 'Changed', 'version': doc['version']}).status_code == 403
    assert client.post(f"/api/documents/{doc['id']}/file", files={'file': ('replacement.png', b'new')}).status_code == 403
    assert client.get(f"/api/documents/{doc['id']}/file").content == b'image'
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
