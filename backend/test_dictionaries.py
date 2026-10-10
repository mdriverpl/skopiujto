import pytest
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login

def test_dictionary_columns_entries_persist_update_and_delete(app_client):
    main, client = app_client
    response = client.post('/api/dictionaries', json={'name': 'Pracownicy', 'fields': ['Imię', 'Nazwisko', 'Telefon']})
    assert response.status_code == 201
    dictionary = response.json()
    path = '/api/dictionaries/' + dictionary['id'] + '/entries'
    item = client.post(path, json={'values': {'Imię': 'Anna', 'Telefon': '+48 600 123 456'}}).json()
    assert item['values']['Nazwisko'] == ''
    main.initialize()
    listing = client.get(path).json()
    assert listing['dictionary']['fields'] == ['Imię', 'Nazwisko', 'Telefon']
    assert listing['dictionary']['count'] == 1 and listing['entries'][0] == item
    body = {'values': {'Imię': 'Anna', 'Nazwisko': 'Kowalska'}, 'version': 1}
    updated = client.put(path + '/' + item['id'], json=body)
    assert updated.status_code == 200 and updated.json()['version'] == 2
    assert client.put(path + '/' + item['id'], json=body).status_code == 409
    assert client.post(path, json={'values': {'Nieznane': 'x'}}).status_code == 422
    assert client.post(path, json={'values': {'Imię': ' '}}).status_code == 422
    assert client.delete(path + '/' + item['id']).status_code == 204
    assert client.get(path).json()['entries'] == []
    client.post(path, json={'values': {'Imię': 'Jan'}})
    assert client.delete('/api/dictionaries/' + dictionary['id']).status_code == 204
    assert client.get('/api/dictionaries').json() == []
    with main.db() as con: assert con.execute('SELECT count(*) FROM dictionary_entries').fetchone()[0] == 0

def test_dictionaries_are_private_and_do_not_change_automatic_ai_data(app_client):
    _, client = app_client
    reader = create_reader(client)
    dictionary = client.post('/api/dictionaries', json={'name': 'Firmy', 'fields': ['Nazwa']}).json()
    path = '/api/dictionaries/' + dictionary['id']
    item = client.post(path + '/entries', json={'values': {'Nazwa': 'Firma'}}).json()
    saved = client.post('/api/saved-data/remember', json={'name': 'Dane', 'fields': {'Miasto': 'Warszawa'}, 'source_key': 'document-one'}).json()
    login(client, READER)
    assert client.get('/api/dictionaries').json() == []
    for method, url, body in [('get', path + '/entries', None), ('post', path + '/entries', {'values': {'Nazwa': 'x'}}),
        ('put', path + '/entries/' + item['id'], {'values': {'Nazwa': 'x'}, 'version': 1}),
        ('delete', path + '/entries/' + item['id'], None), ('delete', path, None)]:
        assert client.request(method, url, json=body).status_code == 404
    login(client, ADMIN)
    assert client.get('/api/saved-data').json() == [saved]
    client.post('/api/saved-data/remember', json={'name': 'Dane', 'fields': {'Miasto': 'Kraków'}, 'source_key': 'document-one'})
    assert client.get('/api/saved-data').json()[0]['fields']['miasto'] == 'Kraków'
    client.post('/api/logout')
    assert client.get('/api/dictionaries').status_code == 401

@pytest.mark.parametrize('body', [{'name': 'AI', 'fields': ['A']}, {'name': ' ', 'fields': ['A']},
    {'name': 'Test', 'fields': ['Imię', ' imię ']}, {'name': 'Test', 'fields': []}])
def test_dictionary_rejects_invalid_schema(app_client, body):
    _, client = app_client
    assert client.post('/api/dictionaries', json=body).status_code == 422
    assert client.get('/api/dictionaries').json() == []

def test_dictionary_rejects_duplicate_names(app_client):
    _, client = app_client
    assert client.post('/api/dictionaries', json={'name': 'Test', 'fields': ['A']}).status_code == 201
    assert client.post('/api/dictionaries', json={'name': 'test', 'fields': ['B']}).status_code == 409

def test_schema_edit_preserves_renamed_values_adds_empty_fields_and_removes_deleted_values(app_client):
    main, client = app_client
    dictionary = client.post('/api/dictionaries', json={'name': 'Pracownicy', 'fields': ['Imię', 'Telefon']}).json()
    path = '/api/dictionaries/' + dictionary['id']
    entry = client.post(path + '/entries', json={'values': {'Imię': 'Anna', 'Telefon': '123'}}).json()
    body = {'name': 'Zespół', 'fields': ['Imię pracownika', 'E-mail'], 'version': dictionary['version'],
        'field_sources': {'Imię pracownika': 'Imię', 'E-mail': None}}
    response = client.put(path, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['dictionary']['version'] == 2 and result['dictionary']['name'] == 'Zespół'
    assert result['entries'][0]['values'] == {'Imię pracownika': 'Anna', 'E-mail': ''}
    assert result['entries'][0]['id'] == entry['id'] and result['entries'][0]['version'] == 2
    assert client.put(path, json=body).status_code == 409
    # An editor using the old entry version cannot overwrite schema changes.
    assert client.put(path + '/entries/' + entry['id'], json={'values': {'E-mail': 'a@example.com'}, 'version': 1}).status_code == 409
    main.initialize()
    assert client.get(path + '/entries').json() == result

def test_schema_edit_checks_owner_mapping_duplicates_and_reserved_ai_name(app_client):
    _, client = app_client
    create_reader(client)
    dictionary = client.post('/api/dictionaries', json={'name': 'Test', 'fields': ['A']}).json()
    path = '/api/dictionaries/' + dictionary['id']
    body = {'name': 'Test', 'fields': ['B'], 'version': 1, 'field_sources': {'B': 'A'}}
    assert client.put('/api/dictionaries/ai', json=body).status_code == 404
    assert client.put(path, json={**body, 'name': 'AI'}).status_code == 422
    assert client.put(path, json={**body, 'field_sources': {'B': 'Missing'}}).status_code == 422
    assert client.put(path, json={**body, 'fields': ['B', 'C'], 'field_sources': {'B': 'A', 'C': 'A'}}).status_code == 422
    login(client, READER)
    assert client.put(path, json=body).status_code == 404
    login(client, ADMIN)
    assert client.get(path + '/entries').json()['dictionary']['version'] == 1

def test_old_dictionary_schema_migrates_without_losing_data(postgres_schema):
    from backend import dictionaries, database
    with database.connect(postgres_schema) as con:
        con.executescript('CREATE TABLE users(id TEXT PRIMARY KEY);' + dictionaries.SCHEMA.replace(',version INTEGER NOT NULL DEFAULT 1);', ');', 1))
        con.execute("INSERT INTO users VALUES('me')")
        con.execute("INSERT INTO dictionaries VALUES('one','me','Test','[\"A\"]','date')")
        dictionaries.initialize(con)
        dictionaries.initialize(con)
        row = con.execute('SELECT * FROM dictionaries').fetchone()
        assert row['name'] == 'Test' and row['version'] == 1
