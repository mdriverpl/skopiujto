from backend import background_worker as worker, webpush
from backend.test_storage import app_client
from backend.test_mail_sync import imap, FakeIMAP
from backend.test_mail_settings import account, encryption_key
from backend.test_access import READER, create_reader
from backend.test_webpush import push_config, subscribe


def test_receive_without_open_browser_and_push_once(app_client, imap, push_config, monkeypatch):
    main, client = app_client
    assert client.put('/api/client-mail/settings', json=account()).status_code == 200
    subscribe(client)
    # Simulate an existing device registration before the incoming messages.
    with main.db() as con:
        con.execute('UPDATE push_subscriptions SET created_at=?',
                    (FakeIMAP.clock.timestamp() - 7200,))
    sent = []
    monkeypatch.setattr(webpush, 'send', lambda sub, body: sent.append(body))
    assert worker.sync_mail(main.db, 24) == 2
    assert worker.sync_mail(main.db, 24) == 0
    worker.dispatch_push(main.db)
    worker.dispatch_push(main.db)
    assert len(sent) == 1  # The second IMAP message is already read.
    assert sent[0]['title'] == 'Nowy e-mail'


def test_failed_mailbox_does_not_stop_other_accounts(app_client, imap, monkeypatch):
    main, client = app_client
    client.put('/api/client-mail/settings', json=account())
    create_reader(client)
    client.post('/api/login', json=READER)
    client.put('/api/client-mail/settings', json=account())
    calls = []
    def receive(*args):
        calls.append(args[1]['id'])
        if len(calls) == 1:
            raise RuntimeError('private error')
        return {'imported': 3, 'remaining': 0, 'skipped': 0}
    monkeypatch.setattr(worker.mail_sync, 'receive', receive)
    assert worker.sync_mail(main.db) == 3
    assert len(calls) == 2


def test_disabled_imap_and_inactive_accounts_skipped(app_client, imap):
    main, client = app_client
    settings = account()
    settings['imap']['enabled'] = False
    client.put('/api/client-mail/settings', json=settings)
    assert worker.sync_mail(main.db) == 0
    assert FakeIMAP.calls == []
    settings['version'] = 1
    settings['imap']['enabled'] = True
    client.put('/api/client-mail/settings', json=settings)
    with main.db() as con:
        con.execute('UPDATE users SET active=0')
    assert worker.sync_mail(main.db) == 0
    assert FakeIMAP.calls == []


def test_overlapping_worker_skips_then_recovers(app_client, monkeypatch):
    main, _ = app_client
    calls = []
    monkeypatch.setattr(webpush, 'dispatch', lambda db: calls.append(True))
    with worker.lease(main.db, 1745026012) as acquired:
        assert acquired
        worker.dispatch_push(main.db)
        assert calls == []
    worker.dispatch_push(main.db)
    assert calls == [True]
