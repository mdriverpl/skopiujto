import io
import time

import pytest
from PIL import Image
from backend.test_storage import app_client, s3, put_params
from botocore.response import StreamingBody
from backend.test_access import ADMIN, READER, create_reader, login
from backend.test_folder_archive import folder, upload
from backend.test_external_shares import create_link
from backend import gallery_uploads


def png():
    output = io.BytesIO()
    Image.new('RGB', (8, 8), 'blue').save(output, 'PNG')
    return output.getvalue()


def gallery(client, enabled=True):
    root = folder(client, 'Gallery')
    link, url = create_link(client, 'folder', root, 'gallery')
    if enabled:
        response = client.patch('/api/external-links/' + link['id'], json={'allow_uploads': True})
        assert response.status_code == 200, response.text
        assert response.json() == {'view_mode': 'gallery', 'allow_uploads': True}
    return root, link, url


def photo(client, url, endpoint='photos', **kwargs):
    return client.post(url + '/' + endpoint, files={'file': ('photo.png', png())}, **kwargs)


def test_contributions_are_opt_in_and_become_owned_gallery_photos(app_client):
    main, client = app_client
    root, link, url = gallery(client, False)
    assert client.get(url).json()['allow_uploads'] is False
    assert client.get(url).json()['can_add_photos'] is True
    assert photo(client, url, 'owner-photos').status_code == 201
    client.post('/api/logout')
    assert photo(client, url).status_code == 403
    assert photo(client, url, 'owner-photos').status_code == 401
    login(client, ADMIN)
    client.patch('/api/external-links/' + link['id'], json={'allow_uploads': True})
    assert client.get('/api/external-links/folder/' + root['id']).json()[0]['allow_uploads']
    client.post('/api/logout')
    response = photo(client, url)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['image'] and result['caption_version'] == 0 and result['likes_count'] == 0
    assert not {'user_id', 'uploaded_by', 'object_bucket', 'object_key', 'visitor_hash'} & result.keys()
    assert any(row['id'] == result['id'] for row in client.get(url).json()['files'])
    assert client.get(url + '/documents/' + result['id'] + '/file').content == png()
    with main.db() as con:
        row = con.execute('SELECT * FROM documents WHERE id=?', (result['id'],)).fetchone()
        assert row['user_id'] == row['uploaded_by'] == root['user_id']
        assert row['folder_id'] == root['id']
        history = con.execute('SELECT * FROM resource_history WHERE resource_id=?', (result['id'],)).fetchone()
        assert history['actor_name'] == 'Odbiorca linku (bez logowania)'
        assert history['actor_id'] == 'external-link:' + link['id']
    login(client, ADMIN)
    assert client.get('/api/documents/' + result['id']).json()['permissions']['delete']
    assert client.patch('/api/external-links/' + link['id'], json={'allow_uploads': False}).status_code == 200
    client.post('/api/logout')
    assert photo(client, url).status_code == 403
    assert client.get(url + '/documents/' + result['id'] + '/file').status_code == 200


def test_folder_scope_owner_permissions_and_separate_link_settings(app_client):
    main, client = app_client
    root, link, url = gallery(client)
    child = folder(client, 'Child', root['id'])
    outside = folder(client, 'Outside')
    _, other_url = create_link(client, 'folder', root, 'gallery')
    create_reader(client)
    login(client, READER)
    assert client.patch('/api/external-links/' + link['id'], json={'allow_uploads': False}).status_code == 404
    assert photo(client, url, 'owner-photos').status_code == 403
    client.post('/api/logout')
    assert photo(client, other_url).status_code == 403
    assert photo(client, url, data={'folder_id': outside['id']}).status_code == 404
    result = photo(client, url, data={'folder_id': child['id']})
    assert result.status_code == 201, result.text
    assert client.get(url, params={'folder_id': child['id']}).json()['files'][0]['id'] == result.json()['id']
    with main.db() as con: con.execute('UPDATE users SET can_add=0 WHERE id=?', (root['user_id'],))
    assert not client.get(url).json()['can_add_photos']
    assert photo(client, url).status_code == 403


def test_image_validation_rejects_non_photos_corruption_and_oversized_uploads(app_client):
    _, client = app_client
    _, _, url = gallery(client)
    client.post('/api/logout')
    for name, data, status in [('evil.html', b'<script>alert(1)</script>', 415),
                               ('evil.png', b'<html>fake image</html>', 415),
                               ('wrong.jpg', png(), 415), ('empty.png', b'', 415),
                               ('x' * 256 + '.png', png(), 422),
                               ('large.png', b'x' * (gallery_uploads.MAX_UPLOAD + 1), 413)]:
        response = client.post(url + '/photos', files={'file': (name, data)})
        assert response.status_code == status, response.text
    assert client.get(url).json()['files'] == []
    response = client.post(url + '/photos', files={'file': ('../photo.png', png())})
    assert response.status_code == 201 and response.json()['filename'] == 'photo.png'


@pytest.mark.parametrize('change', ['disabled', 'revoked', 'expired', 'moved', 'permission'])
def test_revalidate_after_storage_and_cleanup_if_link_or_destination_changes(app_client, monkeypatch, change):
    main, client = app_client
    root, link, url = gallery(client)
    child = folder(client, 'Child', root['id'])
    outside = folder(client, 'Outside')
    cleaned = []
    def store(data, user_id):
        with main.db() as con:
            if change == 'disabled': con.execute('UPDATE external_links SET allow_uploads=0 WHERE id=?', (link['id'],))
            elif change == 'revoked': con.execute('UPDATE external_links SET revoked=1 WHERE id=?', (link['id'],))
            elif change == 'expired': con.execute('UPDATE external_links SET expires=? WHERE id=?', (time.time() - 1, link['id']))
            elif change == 'moved': con.execute('UPDATE folders SET parent_id=? WHERE id=?', (outside['id'], child['id']))
            else: con.execute('UPDATE users SET can_add=0 WHERE id=?', (root['user_id'],))
        return 'test-bucket', 'new-key'
    monkeypatch.setattr(gallery_uploads.storage, 'put', store)
    monkeypatch.setattr(gallery_uploads.storage, 'cleanup', lambda bucket, key: cleaned.append((bucket, key)))
    client.post('/api/logout')
    response = photo(client, url, data={'folder_id': child['id']})
    assert response.status_code in (403, 404, 410), response.text
    assert cleaned == [('test-bucket', 'new-key')]
    with main.db() as con:
        assert con.execute('SELECT count(*) FROM documents').fetchone()[0] == 0
        assert con.execute('SELECT count(*) FROM gallery_uploads').fetchone()[0] == 0


def test_visitor_and_link_quotas_cannot_be_bypassed_by_deleting_photo(app_client):
    main, client = app_client
    root, link, url = gallery(client)
    result = photo(client, url)
    assert result.status_code == 201, result.text
    document = result.json()
    with main.db() as con:
        identity = con.execute('SELECT visitor_hash FROM gallery_uploads').fetchone()[0]
        for index in range(19):
            con.execute('INSERT INTO gallery_uploads(id,link_id,document_id,visitor_hash,created_ts) VALUES(?,?,?,?,?)',
                        (str(index), link['id'], document['id'], identity, time.time()))
    assert client.delete('/api/documents/' + document['id']).status_code == 204
    assert photo(client, url).status_code == 429
    client.cookies.clear()
    assert photo(client, url).status_code == 201
    with main.db() as con:
        for index in range(79):
            con.execute('INSERT INTO gallery_uploads(id,link_id,visitor_hash,created_ts) VALUES(?,?,?,?)',
                        ('total' + str(index), link['id'], 'other', time.time()))
    client.cookies.clear()
    assert photo(client, url).status_code == 429
    login(client, ADMIN)
    assert photo(client, url, 'owner-photos').status_code == 201


def test_single_file_links_do_not_accept_contributions_and_default_is_off(app_client):
    _, client = app_client
    root = folder(client, 'Photos')
    document = upload(client, root, 'photo.png', png())
    result = client.post('/api/external-links/folder/' + root['id'], json={'view_mode': 'gallery', 'allow_uploads': True})
    assert result.status_code == 201 and result.json()['allow_uploads']
    assert client.post('/api/external-links/document/' + document['id'], json={'allow_uploads': True}).status_code == 422
    link, url = create_link(client, 'document', document)
    assert client.patch('/api/external-links/' + link['id'], json={'allow_uploads': True}).status_code == 422
    assert photo(client, url, 'owner-photos').status_code == 422
    assert photo(client, url).status_code == 422


def test_public_upload_uses_s3_and_preserves_original_photo_and_gps(s3):
    from backend.test_photo_location import photo as gps_photo
    main, client, stub = s3
    root, _, url = gallery(client)
    data = gps_photo()
    stub.add_response('put_object', {}, put_params(data))
    client.post('/api/logout')
    response = client.post(url + '/photos', files={'file': ('photo.jpg', data)})
    assert response.status_code == 201, response.text
    identifier = response.json()['id']
    with main.db() as con:
        row = con.execute('SELECT * FROM documents WHERE id=?', (identifier,)).fetchone()
        assert row['file'] is None and row['file_size'] == len(data)
    params = {'Bucket': row['object_bucket'], 'Key': row['object_key']}
    stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(data), len(data))}, params)
    assert client.get(url + '/documents/' + identifier + '/file').content == data
    stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(data), len(data))}, params)
    location = client.get(url + '/documents/' + identifier + '/location')
    assert location.status_code == 200
    assert location.json()['location'] == pytest.approx({'latitude': 52.23, 'longitude': 21.01})
