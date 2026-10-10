from backend.test_storage import app_client
from backend.test_access import create_reader

def test_api_key_read_scope_revocation_and_hash_storage(app_client):
    main, client = app_client
    created = client.post('/api/access-tokens', json={'name': 'Integration'})
    assert created.status_code == 201, created.text
    key = created.json()
    assert key['scope'] == 'read' and key['token'].startswith('edoc_')
    with main.db() as con:
        stored = con.execute('SELECT token_hash FROM api_access_tokens WHERE id=?', (key['id'],)).fetchone()[0]
        assert stored == main.digest(key['token']) and stored != key['token']
    assert key['token'] not in client.get('/api/access-tokens').text
    headers = {'Authorization': 'Bearer ' + key['token']}
    client.cookies.clear()
    assert client.get('/api/documents', headers=headers).status_code == 200
    assert client.post('/api/documents', headers=headers, json={'title': 'Blocked'}).status_code == 403
    assert client.get('/api/documents', headers={'Authorization': 'Bearer invalid'}).status_code == 401
    assert client.get('/api/access-tokens', headers=headers).status_code == 403
    client.post('/api/login', json={'name': 'test-user', 'password': 'test-password-123'})
    assert client.delete('/api/access-tokens/' + key['id']).status_code == 204
    assert client.get('/api/me', headers=headers).status_code == 401

def test_write_api_key_keeps_account_permissions_and_is_revoked_by_reset(app_client):
    _, client = app_client
    reader = create_reader(client)
    key = client.post('/api/access-tokens', json={'name': 'Writer', 'scope': 'write'}).json()
    headers = {'Authorization': 'Bearer ' + key['token']}
    assert client.post('/api/documents', headers=headers, json={'title': 'Via API'}).status_code == 201
    assert client.post('/api/access-tokens', headers=headers, json={'name': 'Another'}).status_code == 403
    client.patch('/api/admin/users/' + reader['id'], json={'can_read': False})
    # Reset of the key owner's password revokes their sessions and API keys.
    account = client.get('/api/me').json()
    assert client.patch('/api/admin/users/' + account['id'], json={'password': 'replacement-password'}).status_code == 200
    assert client.get('/api/me', headers=headers).status_code == 401

def test_api_key_expiry_and_user_isolation_and_openapi(app_client):
    main, client = app_client
    key = client.post('/api/access-tokens', json={'name': 'Expired'}).json()
    with main.db() as con:
        con.execute('UPDATE api_access_tokens SET expires=0 WHERE id=?', (key['id'],))
    assert client.get('/api/me', headers={'Authorization': 'Bearer ' + key['token']}).status_code == 401
    reader = create_reader(client)
    client.post('/api/logout')
    client.post('/api/login', json={'name': 'reader', 'password': 'reader-password-123'})
    assert client.get('/api/access-tokens').json() == []
    assert client.delete('/api/access-tokens/' + key['id']).status_code == 404
    key = client.post('/api/access-tokens', json={'name': 'Reader', 'scope': 'write'}).json()
    assert client.post('/api/documents', headers={'Authorization': 'Bearer ' + key['token']}, json={'title': 'No add permission'}).status_code == 403
    assert client.get('/api/admin/users', headers={'Authorization': 'Bearer ' + key['token']}).status_code == 403
    schema = client.get('/api/openapi.json').json()
    assert 'ApiKeyBearer' in schema['components']['securitySchemes']
    assert '/api/access-tokens' in schema['paths']
    assert client.get('/api/docs').status_code == 200
    assert client.get('/api/health').json() == {'status': 'ok'}
