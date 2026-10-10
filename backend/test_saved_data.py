import pytest

from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login

BODY = {'name': 'Moja firma', 'fields': {'Miejsce zawarcia umowy': 'Warszawa',
        'Adres sprzedającego': 'Długa 1', 'Adres zamawiającego': 'Krótka 2'}}


def test_persistence_version_conflict_and_delete_do_not_change_documents(app_client):
    main, client = app_client
    response = client.post('/api/saved-data', json=BODY)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['fields']['adres sprzedającego'] == 'Długa 1'
    assert saved['fields']['adres zamawiającego'] == 'Krótka 2'
    main.initialize()
    assert client.get('/api/saved-data').json() == [saved]
    update = {**saved, 'fields': {**saved['fields'], 'miejsce zawarcia umowy': 'Kraków'}}
    updated = client.put('/api/saved-data/' + saved['id'], json=update)
    assert updated.status_code == 200 and updated.json()['version'] == 2
    assert client.put('/api/saved-data/' + saved['id'], json=update).status_code == 409
    assert client.get('/api/saved-data').json()[0]['fields']['miejsce zawarcia umowy'] == 'Kraków'
    source = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [
        {'type': 'text', 'text': 'Zawarto w [miejsce zawarcia umowy]'}]}]}
    document = client.post('/api/documents', json={'title': 'Umowa', 'field_source': source,
        'field_values': {'miejsce zawarcia umowy': 'Kraków'}}).json()
    assert client.delete('/api/saved-data/' + saved['id']).status_code == 204
    assert client.get('/api/saved-data').json() == []
    assert client.get('/api/documents/' + document['id']).json()['content'] == 'Zawarto w Kraków'


def test_profiles_are_private_including_admin_and_require_login(app_client):
    _, client = app_client
    admin_profile = client.post('/api/saved-data', json=BODY).json()
    create_reader(client)
    login(client, READER)
    assert client.get('/api/saved-data').json() == []
    assert client.put('/api/saved-data/' + admin_profile['id'], json={**BODY, 'version': 1}).status_code == 404
    assert client.delete('/api/saved-data/' + admin_profile['id']).status_code == 404
    personal = client.post('/api/saved-data', json=BODY)
    assert personal.status_code == 201
    login(client, ADMIN)
    assert client.delete('/api/saved-data/' + personal.json()['id']).status_code == 404
    assert client.get('/api/saved-data').json() == [admin_profile]
    client.post('/api/logout')
    assert client.get('/api/saved-data').status_code == 401
    assert client.post('/api/saved-data', json=BODY).status_code == 401


@pytest.mark.parametrize('extra', [
    {'name': '   '}, {'name': 'a' * 101}, {'fields': {}}, {'fields': {'x': ' '}},
    {'fields': {'x': 'a' * 2001}}, {'fields': {'[x]': 'a'}}, {'fields': {'x\ny': 'a'}},
    {'fields': {'x' * 121: 'a'}}, {'fields': {'X': 'a', ' x ': 'b'}},
    {'fields': {f'pole {i}': 'x' for i in range(201)}},
])
def test_invalid_data_not_saved(app_client, extra):
    _, client = app_client
    assert client.post('/api/saved-data', json={**BODY, **extra}).status_code == 422
    assert client.get('/api/saved-data').json() == []
