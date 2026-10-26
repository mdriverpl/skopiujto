import io
import time

import pytest
from PIL import Image
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login
from backend.test_folder_archive import folder, upload
from backend.test_external_shares import create_link


def setup_photo(client):
    root = folder(client, 'Photos')
    image = io.BytesIO()
    Image.new('RGB', (8, 8), 'blue').save(image, 'PNG')
    row = upload(client, root, 'photo.png', image.getvalue())
    link, url = create_link(client, 'folder', root, 'gallery')
    return root, row, link, url, url + '/documents/' + row['id']


def test_owner_caption_is_public_versioned_and_does_not_modify_file(app_client):
    main, client = app_client
    _, row, _, url, photo = setup_photo(client)
    assert client.get(url + '/permissions').json() == {'can_edit': True}
    body = {'title': '  Holiday  photo ', 'description': 'Short description', 'version': 0}
    response = client.patch(photo + '/caption', json=body)
    assert response.status_code == 200, response.text
    assert response.json()['title'] == 'Holiday photo'
    assert response.json()['caption_version'] == 1
    assert client.patch(photo + '/caption', json=body).status_code == 409
    with main.db() as con:
        document = con.execute('SELECT * FROM documents WHERE id=?', (row['id'],)).fetchone()
        assert document['version'] == row['version'] and document['title'] == row['title']
        assert con.execute('SELECT 1 FROM resource_history WHERE resource_id=? AND action=?',
                           (row['id'], 'Zmieniono nazwę i opis zdjęcia')).fetchone()
    client.post('/api/logout')
    assert client.patch(photo + '/caption', json=body).status_code == 401
    assert client.get(url + '/permissions').status_code == 401
    public = client.get(url).json()['files'][0]
    assert public['description'] == 'Short description' and public['title'] == 'Holiday photo'
    assert not {'user_id', 'visitor_hash', 'object_key'} & public.keys()
    login(client, ADMIN)
    create_reader(client)
    login(client, READER)
    assert client.get(url + '/permissions').json() == {'can_edit': False}
    assert client.patch(photo + '/caption', json=body | {'version': 1}).status_code == 403


def test_likes_idempotent_per_visitor_and_scoped_to_link(app_client):
    _, client = app_client
    _, row, _, url, photo = setup_photo(client)
    _, other_url = create_link(client, 'document', row, 'gallery')
    other = other_url + '/documents/' + row['id']
    client.post('/api/logout')
    first = client.get(photo + '/activity')
    assert first.json() == {'likes_count': 0, 'comments_count': 0, 'liked': False, 'comments': [], 'has_more': False}
    assert 'HttpOnly' in first.headers['set-cookie'] and 'SameSite=lax' in first.headers['set-cookie']
    for _ in range(2):
        response = client.put(photo + '/like', json={'liked': True})
        assert response.status_code == 200, response.text
        assert response.json()['likes_count'] == 1
    assert client.get(url).json()['files'][0]['likes_count'] == 1
    assert client.get(other + '/activity').json()['likes_count'] == 0
    identity = client.cookies.get('gallery_visitor')
    client.cookies.clear()
    assert not client.get(photo + '/activity').json()['liked']
    assert client.put(photo + '/like', json={'liked': True}).json()['likes_count'] == 2
    client.cookies.clear()
    client.cookies.set('gallery_visitor', identity)
    assert client.put(photo + '/like', json={'liked': False}).json()['likes_count'] == 1
    assert not client.get(photo + '/activity').json()['liked']


def test_comments_validation_ownership_moderation_and_rate_limit(app_client):
    _, client = app_client
    _, row, _, _, photo = setup_photo(client)
    _, other_url = create_link(client, 'document', row, 'gallery')
    client.post('/api/logout')
    client.get(photo + '/activity')
    identity = client.cookies.get('gallery_visitor')
    for body in ({'author': ' ', 'content': 'text'}, {'author': 'A', 'content': ' '}, {'author': 'A', 'content': 'x' * 1001}):
        assert client.post(photo + '/comments', json=body).status_code == 422
    response = client.post(photo + '/comments', json={'author': 'Visitor', 'content': '<script>alert(1)</script>'})
    assert response.status_code == 201, response.text
    comment = response.json()
    assert comment['mine'] and 'visitor_hash' not in comment
    assert comment['content'] == '<script>alert(1)</script>'
    assert client.get(other_url + '/documents/' + row['id'] + '/activity').json()['comments'] == []
    client.cookies.clear()
    activity = client.get(photo + '/activity').json()
    assert not activity['comments'][0]['mine'] and activity['comments_count'] == 1
    assert client.delete(photo + '/comments/' + comment['id']).status_code == 404
    client.cookies.clear(); client.cookies.set('gallery_visitor', identity)
    assert client.delete(photo + '/comments/' + comment['id']).status_code == 204
    for _ in range(10):
        response = client.post(photo + '/comments', json={'author': 'Guest', 'content': 'Hello'})
        assert response.status_code == 201, response.text
    assert client.post(photo + '/comments', json={'author': 'Guest', 'content': 'Wait'}).status_code == 429
    last = response.json()
    login(client, ADMIN)
    create_reader(client)
    login(client, READER)
    assert client.delete('/api/gallery-comments/' + last['id']).status_code == 404
    login(client, ADMIN)
    assert client.delete('/api/gallery-comments/' + last['id']).status_code == 204


@pytest.mark.parametrize('state', ['outside', 'moved', 'revoked', 'expired'])
def test_all_photo_actions_enforce_current_link_scope(app_client, state):
    main, client = app_client
    root, row, link, url, photo = setup_photo(client)
    comment = client.post(photo + '/comments', json={'author': 'Guest', 'content': 'Hello'}).json()
    if state == 'outside':
        outside = upload(client, folder(client, 'Outside'), 'outside.png', b'photo')
        photo = url + '/documents/' + outside['id']
    elif state == 'moved':
        with main.db() as con: con.execute('UPDATE documents SET folder_id=NULL WHERE id=?', (row['id'],))
    elif state == 'revoked':
        client.delete('/api/external-links/' + link['id'])
    else:
        with main.db() as con: con.execute('UPDATE external_links SET expires=? WHERE id=?', (time.time() - 1, link['id']))
    for method, suffix, body in [('GET', '/activity', None), ('PUT', '/like', {'liked': True}),
                                  ('POST', '/comments', {'author': 'Guest', 'content': 'Hi'}),
                                  ('PATCH', '/caption', {'title': 'Name', 'version': 0}),
                                  ('DELETE', '/comments/' + comment['id'], None)]:
        response = client.request(method, photo + suffix, json=body) if body is not None else client.request(method, photo + suffix)
        assert response.status_code in (404, 410), response.text


def test_comment_pagination(app_client):
    main, client = app_client
    _, row, link, _, photo = setup_photo(client)
    with main.db() as con:
        for index in range(55):
            con.execute('INSERT INTO photo_comments(id,link_id,document_id,visitor_hash,author,content,created_at,created_ts) VALUES(?,?,?,?,?,?,?,?)',
                        (str(index), link['id'], row['id'], 'test', 'A', str(index), main.now(), index))
    page = client.get(photo + '/activity').json()
    assert page['comments_count'] == 55 and page['has_more']
    assert [int(item['content']) for item in page['comments']] == list(range(5, 55))
    page = client.get(photo + '/activity?offset=50').json()
    assert not page['has_more'] and [int(item['content']) for item in page['comments']] == list(range(5))
