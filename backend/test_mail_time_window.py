from datetime import timedelta
from backend.test_storage import app_client
from backend.test_mail_sync import imap
from backend.test_mail_settings import account, encryption_key
from backend.test_client_mail import imported
from backend.test_access import READER, create_reader, login


def test_default_sync_fetches_only_exact_last_24h_and_batches_metadata(app_client, imap):
    _, client = app_client
    client.put('/api/client-mail/settings', json=account())
    imap.uids = [b'1', b'2', b'3', b'4']
    imap.dates = {b'1': imap.clock - timedelta(hours=1), b'2': imap.clock - timedelta(hours=24),
                  b'3': imap.clock - timedelta(hours=24, seconds=1), b'4': imap.clock - timedelta(days=8)}
    result = client.post('/api/client-mail/sync')
    assert result.status_code == 200, result.text
    assert result.json()['imported'] == 2 and result.json()['remaining'] == 0
    assert [args[0] for command, args in imap.calls if command == 'fetch' and args[1] == '(BODYSTRUCTURE)'] == [b'1', b'2']
    assert len([1 for command, args in imap.calls if command == 'fetch' and args[1] == '(UID RFC822.SIZE FLAGS INTERNALDATE)']) == 1
    assert imap.calls[0] == ('search', (None, 'SINCE', '14-Oct-2026'))
    # Expanding the range imports earlier unseen messages without duplicates.
    assert client.post('/api/client-mail/sync', json={'hours': 48}).json()['imported'] == 1
    assert client.post('/api/client-mail/sync', json={'hours': 168}).json()['imported'] == 0
    assert client.post('/api/client-mail/sync', json={'hours': 720}).json()['imported'] == 1
    assert len(client.get('/api/client-mail').json()) == 4


def test_sync_and_listing_reject_unsupported_ranges_before_contacting_imap(app_client, imap):
    _, client = app_client
    assert client.post('/api/client-mail/sync', json={'hours': 25}).status_code == 422
    assert client.get('/api/client-mail?hours=25').status_code == 422
    assert not imap.calls


def test_listing_limits_transfer_and_can_open_older_report_message_privately(app_client, imap):
    main, client = app_client
    recent = imported(client); older = imported(client)
    with main.db() as con:
        con.execute('UPDATE client_mail SET created_at=? WHERE id=?', ((imap.clock - timedelta(hours=2)).isoformat(), recent['id']))
        con.execute('UPDATE client_mail SET created_at=? WHERE id=?', ((imap.clock - timedelta(hours=26)).isoformat(), older['id']))
    listing = client.get('/api/client-mail?hours=24').json()
    assert [row['id'] for row in listing] == [recent['id']]
    assert listing[0]['attachments'][0]['name'] == 'Oferta.pdf'
    assert len(client.get('/api/client-mail?hours=48').json()) == 2
    report = client.get('/api/client-mail', params={'hours': 24, 'include_id': older['id']}).json()
    assert {row['id'] for row in report} == {recent['id'], older['id']}
    create_reader(client); login(client, READER)
    assert client.get('/api/client-mail', params={'hours': 24, 'include_id': older['id']}).json() == []
