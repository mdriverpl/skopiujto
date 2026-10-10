import io

import pytest
from PIL import Image
from botocore.response import StreamingBody
from botocore.stub import ANY
from backend.test_storage import app_client, s3, put_params
from backend.test_access import READER, create_reader, login

def raster(format='PNG', **options):
    output = io.BytesIO()
    Image.new('RGBA' if format == 'PNG' else 'RGB', (12, 8), (10, 20, 30, 80) if format == 'PNG' else (10, 20, 30)).save(output, format, **options)
    return output.getvalue()

def upload(client, data=None, filename='image.png', **fields):
    return client.post('/api/files', data=fields, files={'file': (filename, data or raster())}).json()

def edit(doc, **extra):
    return {'version': doc['version'], 'x': 2, 'y': 1, 'width': 6, 'height': 4, 'output_width': 3, 'output_height': 2, **extra}

def test_crop_resize_alpha_and_version(app_client):
    _, client = app_client
    doc = upload(client)
    url = f"/api/documents/{doc['id']}/image"
    info = client.get(url).json()
    assert info['can_edit'] and (info['width'], info['height']) == (12, 8)
    saved = client.post(url, json=edit(doc))
    assert saved.status_code == 200, saved.text
    assert saved.json()['version'] == doc['version'] + 1
    with Image.open(io.BytesIO(client.get(f"/api/documents/{doc['id']}/file").content)) as result:
        assert result.size == (3, 2) and result.mode == 'RGBA'
        assert result.getpixel((1, 1))[3] == 80
    assert client.post(url, json=edit(doc)).status_code == 409

@pytest.mark.parametrize('extra,status', [({'x': 10}, 422), ({'width': 0}, 422), ({'output_width': 10001}, 422), ({'output_width': 10000, 'output_height': 10000}, 413), ({'x': 1.5}, 422)])
def test_invalid_edit_preserves_original(app_client, extra, status):
    _, client = app_client
    original = raster()
    doc = upload(client, original)
    assert client.post(f"/api/documents/{doc['id']}/image", json=edit(doc, **extra)).status_code == status
    assert client.get(f"/api/documents/{doc['id']}/file").content == original

def test_exif_orientation_and_tags_preserved(app_client):
    _, client = app_client
    exif = Image.Exif(); exif[274] = 6; exif[271] = 'Test Camera'
    doc = upload(client, raster('JPEG', exif=exif), 'image.jpg')
    url = f"/api/documents/{doc['id']}/image"
    info = client.get(url).json()
    assert (info['width'], info['height']) == (8, 12)
    assert {'name': 'Make', 'value': 'Test Camera'} in info['tags']
    assert client.post(url, json=edit(doc)).status_code == 200
    with Image.open(io.BytesIO(client.get(f"/api/documents/{doc['id']}/file").content)) as result:
        assert result.size == (3, 2)
        assert result.getexif().get(274, 1) == 1
        assert result.getexif()[271] == 'Test Camera'

def test_shared_reader_sees_tags_but_cannot_edit(app_client):
    _, client = app_client
    reader = create_reader(client, can_edit=True)
    folder = client.post('/api/folders', json={'name': 'Images', 'access_mode': 'users', 'user_ids': [reader['id']], 'can_edit': True}).json()
    doc = upload(client, folder_id=folder['id'])
    login(client, READER)
    url = f"/api/documents/{doc['id']}/image"
    assert client.get(url).json()['can_edit'] is False
    assert client.post(url, json=edit(doc)).status_code == 403
    client.post('/api/logout')
    assert client.get(url).status_code == 401

def test_animation_and_unreadable_metadata(app_client):
    _, client = app_client
    output = io.BytesIO()
    Image.new('RGB', (12, 8), 'red').save(output, 'WEBP', save_all=True, append_images=[Image.new('RGB', (12, 8), 'blue')])
    doc = upload(client, output.getvalue(), 'image.webp')
    url = f"/api/documents/{doc['id']}/image"
    assert not client.get(url).json()['can_edit']
    assert client.post(url, json=edit(doc)).status_code == 415
    doc = upload(client, b'<svg/>', 'image.svg')
    info = client.get(f"/api/documents/{doc['id']}/image").json()
    assert not info['can_edit'] and info['tags'][0]['value'] == 'image.svg'

def test_s3_transform_replaces_object(s3):
    main, client, stub = s3
    original = raster()
    stub.add_response('put_object', {}, put_params(original))
    doc = upload(client, original)
    with main.db() as c:
        old_key = c.execute('SELECT object_key FROM documents WHERE id=?', (doc['id'],)).fetchone()[0]
    stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(original), len(original))}, {'Bucket': 'private-test-bucket', 'Key': old_key})
    stub.add_response('put_object', {}, {'Bucket': 'private-test-bucket', 'Key': ANY, 'Body': ANY, 'ContentType': 'application/octet-stream'})
    stub.add_response('delete_object', {}, {'Bucket': 'private-test-bucket', 'Key': old_key})
    assert client.post(f"/api/documents/{doc['id']}/image", json=edit(doc)).status_code == 200
    with main.db() as c:
        row = c.execute('SELECT * FROM documents WHERE id=?', (doc['id'],)).fetchone()
        assert row['object_key'] != old_key and row['file'] is None and row['version'] == doc['version'] + 1

def test_crop_uses_selected_pixels(app_client):
    _, client = app_client
    image = Image.new('RGB', (12, 8), 'red')
    image.paste('blue', (6, 0, 12, 8))
    output = io.BytesIO(); image.save(output, 'PNG')
    doc = upload(client, output.getvalue())
    response = client.post(f"/api/documents/{doc['id']}/image", json=edit(doc, x=6, y=0, width=6, height=8))
    assert response.status_code == 200
    with Image.open(io.BytesIO(client.get(f"/api/documents/{doc['id']}/file").content)) as result:
        assert result.getpixel((0, 0)) == (0, 0, 255)

def test_author_requires_edit_permission_and_private_read(app_client):
    _, client = app_client
    reader = create_reader(client, can_add=True)
    private = client.post('/api/folders', json={'name': 'Private', 'access_mode': 'private'}).json()
    private_doc = upload(client, folder_id=private['id'])
    login(client, READER)
    assert client.get(f"/api/documents/{private_doc['id']}/image").status_code == 404
    doc = upload(client)
    url = f"/api/documents/{doc['id']}/image"
    assert not client.get(url).json()['can_edit']
    assert client.post(url, json=edit(doc)).status_code == 403

def test_s3_failed_save_keeps_original(s3):
    main, client, stub = s3
    original = raster()
    stub.add_response('put_object', {}, put_params(original))
    doc = upload(client, original)
    with main.db() as c:
        old_key = c.execute('SELECT object_key FROM documents WHERE id=?', (doc['id'],)).fetchone()[0]
    stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(original), len(original))}, {'Bucket': 'private-test-bucket', 'Key': old_key})
    stub.add_client_error('put_object', service_error_code='AccessDenied', http_status_code=403)
    assert client.post(f"/api/documents/{doc['id']}/image", json=edit(doc)).status_code == 503
    with main.db() as c:
        row = c.execute('SELECT * FROM documents WHERE id=?', (doc['id'],)).fetchone()
        assert row['object_key'] == old_key and row['version'] == doc['version']
