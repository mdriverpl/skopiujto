import io
import zipfile
import pytest
from backend import folder_archive, storage
from backend.test_storage import app_client
from backend.test_access import create_reader, login, READER


def folder(client, name, parent=None, **extra):
    result = client.post('/api/folders', json={'name': name, 'parent_id': parent, **extra})
    assert result.status_code == 201, result.text
    return result.json()


def upload(client, target, name, data):
    result = client.post('/api/files', data={'folder_id': target['id']}, files={'file': (name, data)})
    assert result.status_code == 201, result.text
    return result.json()


def download(client, target):
    return client.get(f"/api/folders/{target['id']}/archive")


def test_download_includes_full_tree_empty_folders_original_bytes_and_editor_pdfs(app_client):
    _, client = app_client
    root = folder(client, 'Dokumenty')
    child = folder(client, 'Umowy', root['id'])
    folder(client, 'Pusty', child['id'])
    upload(client, root, 'Raport.txt', b'report')
    upload(client, child, 'Umowa.pdf', b'original PDF')
    response = client.post('/api/documents', json={'title': 'Notatka', 'content': 'Zapisane ustalenia', 'folder_id': child['id']})
    assert response.status_code == 201
    outside = folder(client, 'Poza katalogiem')
    upload(client, outside, 'private.txt', b'outside')
    response = download(client, root)
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/zip'
    assert 'Dokumenty.zip' in response.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {'Dokumenty/', 'Dokumenty/Umowy/', 'Dokumenty/Umowy/Pusty/',
                                          'Dokumenty/Raport.txt', 'Dokumenty/Umowy/Umowa.pdf', 'Dokumenty/Umowy/Notatka.pdf'}
        assert archive.read('Dokumenty/Raport.txt') == b'report'
        assert archive.read('Dokumenty/Umowy/Umowa.pdf') == b'original PDF'
        assert archive.read('Dokumenty/Umowy/Notatka.pdf').startswith(b'%PDF-')


def test_archive_excludes_private_children_and_requires_readable_root(app_client):
    _, client = app_client
    reader = create_reader(client)
    root = folder(client, 'Shared', access_mode='users', user_ids=[reader['id']])
    child = folder(client, 'Readable', root['id'])
    hidden = folder(client, 'Hidden', root['id'], access_mode='private')
    upload(client, child, 'visible.txt', b'visible')
    upload(client, hidden, 'secret.txt', b'private')
    login(client, READER)
    assert download(client, hidden).status_code == 404
    result = download(client, root)
    assert result.status_code == 200, result.text
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert set(archive.namelist()) == {'Shared/', 'Shared/Readable/', 'Shared/Readable/visible.txt'}
    client.post('/api/logout')
    assert download(client, root).status_code == 401


def test_name_collisions_never_overwrite_entries_or_create_unsafe_archive_paths(app_client):
    _, client = app_client
    root = folder(client, 'CON')
    folder(client, 'report.txt', root['id'])
    upload(client, root, 'report.txt', b'one')
    upload(client, root, 'report.txt', b'two')
    with zipfile.ZipFile(io.BytesIO(download(client, root).content)) as archive:
        assert set(archive.namelist()) == {'_CON/', '_CON/report.txt/', '_CON/report (2).txt', '_CON/report (3).txt'}
        assert {archive.read(name) for name in archive.namelist() if not name.endswith('/')} == {b'one', b'two'}
    assert '/' not in folder_archive.safe_name('../bad/name')
    assert '\\' not in folder_archive.safe_name('..\\bad\\name')


def test_s3_files_are_copied_without_changes_and_stream_is_closed(app_client, monkeypatch):
    main, client = app_client
    root = folder(client, 'Objects')
    file = upload(client, root, 'object.bin', b'placeholder')
    with main.db() as con:
        con.execute('UPDATE documents SET file=NULL,object_bucket=?,object_key=? WHERE id=?', ('bucket', 'key', file['id']))
    class Body(io.BytesIO):
        def iter_chunks(self, chunk_size):
            while part := self.read(chunk_size): yield part
    body = Body(b'object bytes')
    monkeypatch.setattr(storage, 'get', lambda bucket, key: body)
    result = download(client, root)
    assert result.status_code == 200, result.text
    assert body.closed
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert archive.read('Objects/object.bin') == b'object bytes'


def test_missing_file_fails_download_instead_of_returning_incomplete_zip(app_client):
    main, client = app_client
    root = folder(client, 'Incomplete')
    file = upload(client, root, 'missing.txt', b'content')
    with main.db() as con: con.execute('UPDATE documents SET file=NULL,object_key=NULL WHERE id=?', (file['id'],))
    assert download(client, root).status_code == 503
