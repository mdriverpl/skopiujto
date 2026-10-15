from backend import ai, mail_daily
from backend.test_storage import app_client
from backend.test_access import READER, create_reader, login


def seed(main):
    with main.db() as con:
        owner = con.execute("SELECT id FROM users WHERE name='test-user'").fetchone()['id']
        for identifier, timestamp, folder, category, sender, label in [
            ('client', '2026-10-14T22:30:00Z', 'inbox', 'invoice', 'client@secret.example.com', 'reply'),
            ('spam', '2026-10-15T21:59:59Z', 'spam', 'invoice', 'spam@secret.example.com', 'urgent'),
            ('next', '2026-10-15T22:00:00Z', 'inbox', '', 'next@secret.example.com', ''),
            ('archive', '2026-10-15T12:00:00', 'archive', 'advertisement', 'ad@secret.example.com', ''),
            ('sent', '2026-10-15T12:00:00Z', 'sent', '', 'me@secret.example.com', ''),
            ('draft', '2026-10-15T12:00:00Z', 'drafts', '', 'me@secret.example.com', ''),
            ('trash', '2026-10-15T12:00:00Z', 'trash', '', 'old@secret.example.com', ''),
            ('bad-date', 'invalid', 'inbox', '', 'bad@secret.example.com', ''),
        ]:
            con.execute('''INSERT INTO client_mail(id,user_id,sender_name,sender_email,recipient,subject,
                content,folder,category,label,unread,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,1,?)''',
                (identifier, owner, 'SECRET NAME', sender, 'private@secret.example.com', 'SECRET SUBJECT',
                 'SECRET BODY', folder, category, label, timestamp))


def test_daily_statistics_use_warsaw_boundaries_all_folders_and_company_rules(app_client):
    main, client = app_client
    seed(main)
    response = client.post('/api/client-mail/client/company', json={'version': 1, 'name': 'SECRET COMPANY'})
    assert response.status_code == 200, response.text
    response = client.get('/api/client-mail/day-report?day=2026-10-15')
    assert response.status_code == 200, response.text
    report = response.json(); stats = report['stats']
    assert report['timezone'] == 'Europe/Warsaw'
    assert stats['total'] == 5 and stats['received'] == 4 and stats['sent'] == 1
    assert stats['spam'] == 1 and stats['clients'] == 1 and stats['reply'] == 1 and stats['urgent'] == 0
    assert stats['unread'] == 4
    assert stats['categories']['invoice'] == 1
    assert stats['categories']['spam'] == 1
    assert stats['categories']['advertisement'] == 1
    assert stats['categories']['uncategorized'] == 1
    assert sum(stats['categories'].values()) == stats['received']
    assert report['companies'][0]['name'] == 'SECRET COMPANY'


def test_local_daily_analysis_never_calls_external_ai(app_client, monkeypatch):
    main, client = app_client
    seed(main)
    async def forbidden(*args): raise AssertionError('External AI must not be called')
    monkeypatch.setattr(ai, 'structured_response', forbidden)
    result = client.post('/api/client-mail/day-report', json={'day': '2026-10-15'})
    assert result.status_code == 200, result.text
    assert result.json()['engine'] == 'local'
    assert 'Odebrane: 4' in result.json()['analysis']['summary']


def test_local_report_is_recomputed_when_categories_change_and_does_not_allow_external_ai(app_client, monkeypatch):
    main, client = app_client
    seed(main)
    async def forbidden(*args): raise AssertionError('External AI must not be called')
    monkeypatch.setattr(ai, 'structured_response', forbidden)
    body = {'day': '2026-10-15'}
    first = client.post('/api/client-mail/day-report', json=body)
    assert first.status_code == 200, first.text
    assert first.json()['engine'] == 'local'
    assert first.json()['stats']['categories']['notification'] == 0
    client.patch('/api/client-mail/trash', json={'version': 1, 'category': 'notification'})
    refreshed = client.post('/api/client-mail/day-report', json=body).json()
    assert refreshed['stats']['categories']['notification'] == 1
    assert refreshed['stats']['categories']['uncategorized'] == 0
    assert client.post('/api/client-mail/day-report', json={**body, 'use_ai': True}).json()['engine'] == 'local'


def test_reports_are_private_and_dates_validated(app_client):
    main, client = app_client
    seed(main)
    create_reader(client); login(client, READER)
    report = client.post('/api/client-mail/day-report', json={'day': '2026-10-15'}).json()
    assert report['stats']['total'] == 0 and report['companies'] == []
    assert report['messages'] == []
    assert client.post('/api/client-mail/day-report', json={'day': '2026-02-31'}).status_code == 422
    assert client.get('/api/client-mail/day-report?day=invalid').status_code == 422
    client.post('/api/logout')
    assert client.get('/api/client-mail/day-report').status_code == 401
    assert client.post('/api/client-mail/day-report', json={'day': '2026-10-15'}).status_code == 401


def test_empty_day_and_daylight_saving_boundaries_are_local(app_client, monkeypatch):
    main, client = app_client
    seed(main)
    async def forbidden(*args): raise AssertionError('External AI must not be called')
    monkeypatch.setattr(ai, 'structured_response', forbidden)
    result = client.post('/api/client-mail/day-report', json={'day': '2026-10-10'}).json()
    assert result['stats']['total'] == 0 and result['engine'] == 'local'
    assert mail_daily.parsed_day('2026-10-25T22:59:59Z').isoformat() == '2026-10-25'
    assert mail_daily.parsed_day('2026-10-25T23:00:00Z').isoformat() == '2026-10-26'


def test_report_lists_urgent_reply_payment_and_info_without_spam_or_foreign_days(app_client):
    main, client = app_client
    seed(main)
    with main.db() as con:
        con.execute("UPDATE client_mail SET label='urgent' WHERE id='archive'")
        con.execute("UPDATE client_mail SET label='payment' WHERE id='trash'")
    report = client.post('/api/client-mail/day-report', json={'day': '2026-10-15'}).json()
    assert report['stats']['urgent'] == 1
    assert report['stats']['reply'] == 1
    assert report['stats']['payment'] == 1
    assert report['stats']['info'] == 0
    rows = {row['id']: row for row in report['messages']}
    assert set(rows) == {'client', 'archive', 'spam', 'trash', 'sent'}
    assert rows['archive']['label'] == 'urgent' and not rows['archive']['spam']
    assert rows['spam']['spam'] and rows['spam']['category'] == 'spam'
    assert rows['sent']['direction'] == 'sent'
    assert rows['client']['subject'] == 'SECRET SUBJECT'
    assert rows['client']['sender_email'] == 'client@secret.example.com'
    assert 'content' not in rows['client'] and 'attachments' not in rows['client']
    assert 'Pilne: 1' in report['analysis']['summary']
    assert 'Do zapłaty: 1' in report['analysis']['summary']
    with main.db() as con:
        con.execute("UPDATE client_mail SET label='info' WHERE id='archive'")
    refreshed = client.get('/api/client-mail/day-report?day=2026-10-15').json()
    assert refreshed['stats']['urgent'] == 0 and refreshed['stats']['info'] == 1
