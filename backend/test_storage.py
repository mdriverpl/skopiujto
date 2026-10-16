import importlib
import io
import os
import secrets
from urllib.parse import urlencode, quote

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber
from fastapi.testclient import TestClient
import psycopg
from psycopg import sql


@pytest.fixture
def postgres_schema(monkeypatch):
    test_url = os.getenv('EDOCUMENTS_TEST_DATABASE_URL')
    if not test_url:
        pytest.fail('Set EDOCUMENTS_TEST_DATABASE_URL to an isolated PostgreSQL test database.')
    schema = 'test_' + secrets.token_hex(12)
    with psycopg.connect(test_url, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    separator = '&' if '?' in test_url else '?'
    url = test_url + separator + urlencode({'options': f'-c search_path={schema}'}, quote_via=quote)
    monkeypatch.setenv('DATABASE_SCHEMA', schema)
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setenv('EDOCUMENTS_STORAGE', 'database')
    try:
        yield url
    finally:
        with psycopg.connect(test_url, autocommit=True) as admin:
            admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


@pytest.fixture
def app_client(postgres_schema, monkeypatch, tmp_path):
    monkeypatch.setenv('EDOCUMENTS_MAIL_ATTACHMENTS_DIR', str(tmp_path / 'mail-attachments'))
    main = importlib.import_module('backend.main')
    monkeypatch.setattr(main, 'DATABASE_URL', postgres_schema)
    main.initialize()
    with TestClient(main.app) as client:
        response = client.post('/api/setup', json={'name': 'test-user', 'password': 'test-password-123'})
        assert response.status_code == 201
        yield main, client


@pytest.fixture
def s3(app_client, monkeypatch):
    main, client = app_client
    monkeypatch.setenv('EDOCUMENTS_STORAGE', 's3')
    monkeypatch.setenv('S3_BUCKET', 'private-test-bucket')
    sdk = boto3.client('s3', endpoint_url='https://s3.example.invalid', region_name='us-east-1',
                       aws_access_key_id='test', aws_secret_access_key='test')
    monkeypatch.setattr(main.storage, 'client', lambda: sdk)
    with Stubber(sdk) as stub:
        yield main, client, stub
        stub.assert_no_pending_responses()


def put_params(data):
    return {'Bucket': 'private-test-bucket', 'Key': ANY, 'Body': data, 'ContentType': 'application/octet-stream'}


def test_s3_upload_download_share_replace_delete(s3):
    main, client, stub = s3
    stub.add_response('put_object', {}, put_params(b'hello'))
    uploaded = client.post('/api/files', files={'file': ('plik.txt', b'hello')})
    assert uploaded.status_code == 201
    doc = uploaded.json()
    assert doc['has_file'] and 'object_key' not in doc and 'object_bucket' not in doc
    with main.db() as con:
        row = con.execute('SELECT * FROM documents WHERE id=?', (doc['id'],)).fetchone()
    assert row['file'] is None and row['file_size'] == 5
    old_key = row['object_key']
    assert old_key.startswith('edokumenty/')
    assert client.get('/api/documents').json()[0]['file_size'] == 5
    params = {'Bucket': 'private-test-bucket', 'Key': old_key}
    stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(b'hello'), 5)}, params)
    response = client.get(f"/api/documents/{doc['id']}/file")
    assert response.content == b'hello'
    assert response.headers['content-disposition'].startswith('attachment;')
    share = client.post(f"/api/documents/{doc['id']}/shares", json={'hours': 1}).json()
    token = share['path'].split('/')[-1]
    client.post('/api/logout')
    assert client.get(f"/api/documents/{doc['id']}/file").status_code == 401
    stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(b'hello'), 5)}, params)
    assert client.get(f'/api/shared/{token}/file').content == b'hello'
    client.post('/api/login', json={'name': 'test-user', 'password': 'test-password-123'})
    stub.add_response('put_object', {}, put_params(b'new'))
    stub.add_response('delete_object', {}, params)
    replaced = client.post(f"/api/documents/{doc['id']}/file", files={'file': ('nowy.txt', b'new')})
    assert replaced.status_code == 200
    with main.db() as con:
        new_key = con.execute('SELECT object_key FROM documents WHERE id=?', (doc['id'],)).fetchone()[0]
    assert new_key != old_key
    stub.add_response('delete_object', {}, {'Bucket': 'private-test-bucket', 'Key': new_key})
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get('/api/documents').json() == []


def test_failed_s3_upload_does_not_create_document(s3):
    main, client, stub = s3
    stub.add_client_error('put_object', 'AccessDenied', http_status_code=403, expected_params=put_params(b'hello'))
    assert client.post('/api/files', files={'file': ('plik.txt', b'hello')}).status_code == 503
    assert client.get('/api/documents').json() == []


def test_failed_database_write_cleans_uploaded_object(s3, monkeypatch):
    main, client, stub = s3
    stub.add_response('put_object', {}, put_params(b'hello'))
    stub.add_response('delete_object', {}, {'Bucket': 'private-test-bucket', 'Key': ANY})
    with main.db() as con:
        con.execute("CREATE FUNCTION fail_upload() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test failure' USING ERRCODE='23514'; END $$")
        con.execute('CREATE TRIGGER fail_upload BEFORE INSERT ON documents FOR EACH ROW EXECUTE FUNCTION fail_upload()')
    with pytest.raises(main.database.IntegrityError):
        client.post('/api/files', files={'file': ('plik.txt', b'hello')})


def test_missing_bucket_fails_closed(s3, monkeypatch):
    main, client, stub = s3
    monkeypatch.delenv('S3_BUCKET')
    assert client.post('/api/files', files={'file': ('plik.txt', b'hello')}).status_code == 503
    assert client.get('/api/documents').json() == []


def test_database_files_remain_available_with_s3_enabled(s3):
    main, client, stub = s3
    doc = client.post('/api/documents', json={'title': 'Legacy'}).json()
    with main.db() as con:
        con.execute('UPDATE documents SET filename=?,file=? WHERE id=?', ('legacy.txt', b'old', doc['id']))
    assert client.get('/api/documents').json()[0]['file_size'] == 3
    assert client.get(f"/api/documents/{doc['id']}/file").content == b'old'


def test_upload_limits_and_ownership(s3):
    main, client, stub = s3
    assert client.post('/api/files', files={'file': ('large.bin', b'x' * (main.MAX_UPLOAD + 1))}).status_code == 413
    assert client.post('/api/documents/missing/file', files={'file': ('plik.txt', b'hello')}).status_code == 404
    assert client.get('/api/documents').json() == []


def test_folders_nested_upload_and_deletion(app_client):
    main, client = app_client
    root = client.post('/api/folders', json={'name': 'Umowy'}).json()
    child_response = client.post('/api/folders', json={'name': '2026', 'parent_id': root['id']})
    assert child_response.status_code == 201
    child = child_response.json()
    assert len(client.get('/api/folders').json()) == 2
    upload = client.post('/api/files', data={'folder_id': child['id']}, files={'file': ('umowa.txt', b'contract')})
    assert upload.status_code == 201
    doc = upload.json()
    assert doc['folder_id'] == child['id']
    listed = client.get('/api/documents').json()[0]
    assert listed['folder_id'] == child['id'] and listed['user_id'] == root['user_id']
    assert client.delete(f"/api/folders/{root['id']}").status_code == 409
    assert client.delete(f"/api/folders/{child['id']}").status_code == 409
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get(f"/api/documents/{doc['id']}/file").status_code == 404
    assert client.delete(f"/api/folders/{child['id']}").status_code == 204
    assert client.delete(f"/api/folders/{root['id']}").status_code == 204
    assert client.get('/api/folders').json() == []


def test_folder_names_and_parent_validation(app_client):
    main, client = app_client
    for name in [' ', '..', '.', 'a/b', 'a\\b', 'a\x00b']:
        assert client.post('/api/folders', json={'name': name}).status_code == 422
    assert client.post('/api/folders', json={'name': 'One'}).status_code == 201
    assert client.post('/api/folders', json={'name': ' one '}).status_code == 409
    assert client.post('/api/folders', json={'name': 'Child', 'parent_id': 'missing'}).status_code == 404
    assert client.post('/api/files', data={'folder_id': 'missing'}, files={'file': ('test.txt', b'test')}).status_code == 404
    assert client.get('/api/documents').json() == []


def test_other_user_cannot_delete_files_or_folders(s3):
    main, client, stub = s3
    root = client.post('/api/folders', json={'name': 'Private'}).json()
    stub.add_response('put_object', {}, put_params(b'private'))
    doc = client.post('/api/files', data={'folder_id': root['id']}, files={'file': ('test.txt', b'private')}).json()
    with main.db() as con:
        con.execute('INSERT INTO users(id,name,password) VALUES(?,?,?)', ('other-user', 'other', main.password_hash('other-password-123')))
    client.post('/api/logout')
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 401
    assert client.delete(f"/api/folders/{root['id']}").status_code == 401
    assert client.post('/api/login', json={'name': 'other', 'password': 'other-password-123'}).status_code == 200
    assert client.get('/api/documents').json() == []
    assert client.get('/api/folders').json() == []
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 404
    assert client.delete(f"/api/folders/{root['id']}").status_code == 404
    assert client.post('/api/folders', json={'name': 'Intruder', 'parent_id': root['id']}).status_code == 404
    assert client.post('/api/files', data={'folder_id': root['id']}, files={'file': ('test.txt', b'test')}).status_code == 404
    assert client.post(f"/api/documents/{doc['id']}/file", files={'file': ('test.txt', b'test')}).status_code == 404
    with main.db() as con:
        assert con.execute('SELECT count(*) FROM documents').fetchone()[0] == 1
        assert con.execute('SELECT count(*) FROM folders').fetchone()[0] == 1


def test_s3_deletion_failure_keeps_file_metadata(s3):
    main, client, stub = s3
    stub.add_response('put_object', {}, put_params(b'hello'))
    doc = client.post('/api/files', files={'file': ('test.txt', b'hello')}).json()
    stub.add_client_error('delete_object', 'AccessDenied', http_status_code=403,
                          expected_params={'Bucket': 'private-test-bucket', 'Key': ANY})
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 503
    assert client.get('/api/documents').json()[0]['id'] == doc['id']
