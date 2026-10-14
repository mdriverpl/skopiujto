from backend.test_storage import app_client
from backend.test_access import READER, create_reader, login


def test_notes_create_edit_searchable_list_delete_and_conflict(app_client):
    _, client = app_client
    response = client.post('/api/notes', json={'title': '  Ustalenia  ', 'content': 'Oferta w piątek'})
    assert response.status_code == 201, response.text
    note = response.json()
    assert note['title'] == 'Ustalenia' and note['version'] == 1
    assert client.get('/api/notes').json() == [note]
    url = '/api/notes/' + note['id']
    updated = client.patch(url, json={'title': 'Nowe ustalenia', 'content': 'Oferta w środę', 'version': 1})
    assert updated.status_code == 200 and updated.json()['version'] == 2
    assert client.patch(url, json={'title': 'Stary zapis', 'version': 1}).status_code == 409
    assert client.get('/api/notes').json()[0]['content'] == 'Oferta w środę'
    assert client.delete(url).status_code == 204
    assert client.get('/api/notes').json() == []


def test_notes_are_private_even_from_other_users_and_require_login(app_client):
    _, client = app_client
    note = client.post('/api/notes', json={'title': 'Prywatna', 'content': 'Sekret'}).json()
    create_reader(client)
    login(client, READER)
    assert client.get('/api/notes').json() == []
    url = '/api/notes/' + note['id']
    assert client.patch(url, json={'title': 'Zmiana', 'version': 1}).status_code == 404
    assert client.delete(url).status_code == 404
    # Personal notes are independent of document/folder write permissions.
    assert client.post('/api/notes', json={'title': 'Moja notatka'}).status_code == 201
    client.post('/api/logout')
    assert client.get('/api/notes').status_code == 401
    assert client.post('/api/notes', json={'title': 'Bez sesji'}).status_code == 401
    assert client.patch(url, json={'title': 'Zmiana', 'version': 1}).status_code == 401
    assert client.delete(url).status_code == 401


def test_note_validation(app_client):
    _, client = app_client
    for body in ({'title': ' '}, {'title': 'x' * 201}, {'title': 'Tytuł', 'content': 'x' * 20001}):
        assert client.post('/api/notes', json=body).status_code == 422
    assert client.get('/api/notes').json() == []
