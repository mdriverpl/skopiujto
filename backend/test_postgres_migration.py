import os
import secrets
import hashlib
import pytest
import psycopg
from psycopg import sql
from fastapi.testclient import TestClient
from backend import database, migrate_postgres
from backend.test_storage import app_client

def test_migration_copies_every_row_preserves_binary_and_refuses_overwrite(app_client, tmp_path, monkeypatch):
    main, _ = app_client
    url = os.getenv('EDOCUMENTS_TEST_DATABASE_URL')
    if not url: pytest.skip('Requires a separate PostgreSQL test database')
    source = tmp_path / 'source.sqlite3'
    schema = 'migration_' + secrets.token_hex(10)
    with monkeypatch.context() as patch:
        patch.setattr(main, 'DATABASE_URL', '')
        patch.setattr(main, 'DB_PATH', source)
        patch.setenv('DATABASE_SCHEMA', schema)
        main.initialize()
        with TestClient(main.app) as client:
            account = client.post('/api/setup', json={'name': 'Migrated', 'password': 'migration-password-123'}).json()
            parent = client.post('/api/folders', json={'name': 'Parent'}).json()
            child = client.post('/api/folders', json={'name': 'Child', 'parent_id': parent['id']}).json()
            doc = client.post('/api/files', data={'folder_id': child['id']}, files={'file': ('data.bin', b'\x00\xff\x01')} ).json()
            key = client.post('/api/access-tokens', json={'name': 'Kept key'}).json()
        before = hashlib.sha256(source.read_bytes()).digest()
        try:
            with monkeypatch.context() as failure:
                def fail(*args):
                    raise ValueError('Forced verification failure')
                failure.setattr(migrate_postgres, 'fingerprint', fail)
                with pytest.raises(ValueError, match='Forced'):
                    migrate_postgres.migrate(source, url, tmp_path / 'backups')
            with psycopg.connect(url) as con:
                assert not con.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (schema,)).fetchone()
            backup, counts = migrate_postgres.migrate(source, url, tmp_path / 'backups')
            assert backup.is_file() and counts['users'] == 1 and counts['folders'] == 2
            assert counts['documents'] == 1 and counts['resource_history'] == 3
            assert hashlib.sha256(source.read_bytes()).digest() == before
            with database.connect(url) as con:
                row = con.execute('SELECT * FROM documents WHERE id=?', (doc['id'],)).fetchone()
                assert row['file'] == b'\x00\xff\x01' and row['folder_id'] == child['id']
                assert con.execute('SELECT user_id FROM api_access_tokens').fetchone()[0] == account['id']
            with pytest.raises(ValueError, match='pusty'):
                migrate_postgres.migrate(source, url, tmp_path / 'backups')
            patch.setattr(main, 'DATABASE_URL', url)
            main.initialize()
            with TestClient(main.app) as client:
                headers = {'Authorization': 'Bearer ' + key['token']}
                assert client.get('/api/documents/' + doc['id'] + '/file', headers=headers).content == b'\x00\xff\x01'
                assert client.post('/api/login', json={'name': 'Migrated', 'password': 'migration-password-123'}).status_code == 200
        finally:
            with psycopg.connect(url, autocommit=True) as con:
                con.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
