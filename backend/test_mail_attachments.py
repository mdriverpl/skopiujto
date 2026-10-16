import pytest
from fastapi import HTTPException
from backend import mail_attachments
from backend.test_storage import app_client
from backend.test_mail_sync import imap
from backend.test_mail_settings import account, encryption_key
from backend.test_client_mail import imported, eml


def test_sync_keeps_only_metadata_and_download_fetches_one_part_once(app_client, imap):
    main, client = app_client
    client.put('/api/client-mail/settings', json=account())
    assert client.post('/api/client-mail/sync').status_code == 200
    messages = client.get('/api/client-mail').json()
    assert len(messages) == 2
    assert all('BODY.PEEK[]' not in args[1] and 'BODY.PEEK[2]<' not in args[1]
               for command, args in imap.calls if command == 'fetch')
    with main.db() as con:
        parts = con.execute('SELECT * FROM client_mail_attachments').fetchall()
        assert all(p['data'] is None and p['disk_key'] is None and p['remote_section'] == '2' for p in parts)
    assert not mail_attachments.root().exists()
    row = messages[0]
    url = f"/api/client-mail/{row['id']}/attachments/{row['attachments'][0]['id']}"
    imap.calls.clear()
    result = client.get(url)
    assert result.status_code == 200, result.text
    assert result.content == b'PDF bytes'
    assert len(imap.calls) == 2
    assert all(args[0] in (b'1', b'2') for _, args in imap.calls)
    with main.db() as con:
        part = con.execute('SELECT * FROM client_mail_attachments WHERE id=?', (row['attachments'][0]['id'],)).fetchone()
        assert part['data'] is None and part['size'] == 9
        assert mail_attachments.disk_path(part['disk_key']).read_bytes() == b'PDF bytes'
    imap.calls.clear()
    assert client.get(url).content == b'PDF bytes'
    assert not imap.calls


def test_spam_is_never_fetched_or_saved_and_can_be_restored(app_client, imap):
    main, client = app_client
    client.put('/api/client-mail/settings', json=account())
    # Block sender before receiving another message from this address.
    first = imported(client)
    client.post(f"/api/client-mail/{first['id']}/spam-address", json={'version': first['version']})
    before = set(mail_attachments.root().rglob('*'))
    assert client.post('/api/client-mail/sync').status_code == 200
    row = next(m for m in client.get('/api/client-mail').json() if m['id'] != first['id'])
    assert row['folder'] == 'spam' and row['attachments_blocked']
    url = f"/api/client-mail/{row['id']}/attachments/{row['attachments'][0]['id']}"
    imap.calls.clear()
    assert client.get(url).status_code == 422
    assert not imap.calls and set(mail_attachments.root().rglob('*')) == before
    result = client.post('/api/client-mail/import', files={'file': ('spam.eml', eml())})
    assert result.status_code == 201 and result.json()['attachments_blocked']
    assert set(mail_attachments.root().rglob('*')) == before
    row = client.patch(f"/api/client-mail/{row['id']}", json={'version': row['version'], 'folder': 'inbox'}).json()
    assert not row['attachments_blocked']
    assert client.get(url).content == b'PDF bytes'


def test_uidvalidity_or_account_change_does_not_fetch_wrong_attachment(app_client, imap):
    main, client = app_client
    client.put('/api/client-mail/settings', json=account())
    client.post('/api/client-mail/sync')
    row = client.get('/api/client-mail').json()[0]
    url = f"/api/client-mail/{row['id']}/attachments/{row['attachments'][0]['id']}"
    imap.validity = b'999'
    imap.calls.clear()
    assert client.get(url).status_code == 409
    assert not imap.calls and not mail_attachments.root().exists()
    imap.validity = b'123'
    body = account(); body['imap']['host'] = 'different.example.com'; body['version'] = 1
    assert client.put('/api/client-mail/settings', json=body).status_code == 200
    assert client.get(url).status_code == 409
    assert not imap.calls


def test_legacy_bytes_are_preserved_then_migrated_on_access(app_client):
    main, client = app_client
    row = imported(client)
    part_id = row['attachments'][0]['id']
    with main.db() as con:
        con.execute('UPDATE client_mail_attachments SET data=?,disk_key=NULL WHERE id=?', (b'legacy PDF', part_id))
    url = f"/api/client-mail/{row['id']}/attachments/{part_id}"
    assert client.get(url).content == b'legacy PDF'
    with main.db() as con:
        part = con.execute('SELECT * FROM client_mail_attachments WHERE id=?', (part_id,)).fetchone()
        assert part['data'] is None
        assert mail_attachments.disk_path(part['disk_key']).read_bytes() == b'legacy PDF'


def test_spam_action_during_remote_fetch_prevents_disk_save(app_client, imap, monkeypatch):
    main, client = app_client
    client.put('/api/client-mail/settings', json=account())
    client.post('/api/client-mail/sync')
    row = client.get('/api/client-mail').json()[0]
    def fetch(*args):
        with main.db() as con:
            con.execute("UPDATE client_mail SET folder='spam' WHERE id=?", (row['id'],))
        return b'PDF bytes'
    monkeypatch.setattr(mail_attachments, 'fetch', fetch)
    result = client.get(f"/api/client-mail/{row['id']}/attachments/{row['attachments'][0]['id']}")
    assert result.status_code == 422
    assert not mail_attachments.root().exists()


def test_failed_legacy_disk_write_keeps_database_copy(app_client, monkeypatch):
    main, client = app_client
    row = imported(client)
    part_id = row['attachments'][0]['id']
    with main.db() as con:
        con.execute('UPDATE client_mail_attachments SET data=?,disk_key=NULL WHERE id=?', (b'legacy PDF', part_id))
    def fail(*args): raise HTTPException(503, 'Disk unavailable')
    monkeypatch.setattr(mail_attachments, 'put', fail)
    assert client.get(f"/api/client-mail/{row['id']}/attachments/{part_id}").status_code == 503
    with main.db() as con:
        part = con.execute('SELECT data,disk_key FROM client_mail_attachments WHERE id=?', (part_id,)).fetchone()
        assert bytes(part['data']) == b'legacy PDF' and part['disk_key'] is None


def test_structure_handles_nested_lists_literals_and_escaped_quotes():
    data = [(b'1 (BODYSTRUCTURE (("TEXT" "PLAIN" NIL NIL NIL "7BIT" 20 1)', b''),
            b'("APPLICATION" "PDF" ("NAME" {7}\r\na\"b.pdf) NIL NIL "BASE64" 100) "MIXED"))']
    parts = list(mail_attachments.leaves(mail_attachments.structure(data)))
    assert [section for section, _ in parts] == ['1', '2']
    assert parts[1][1][2][1] == 'a"b.pdf'
    for key in ('../file', 'a/' + 'b' * 48, '/etc/passwd'):
        with pytest.raises(HTTPException): mail_attachments.disk_path(key)
