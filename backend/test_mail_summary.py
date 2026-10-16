from backend.test_storage import app_client
from backend.test_access import READER, create_reader, login
from datetime import datetime, timezone
from backend import mail_sync


def test_summary_counts_only_current_users_nonspam_inbox_without_marking_read(app_client):
    main, client = app_client
    user_id = client.get('/api/me').json()['id']
    rows = [('new', 'inbox', 1, '', ''), ('urgent', 'inbox', 1, 'urgent', ''),
            ('read', 'inbox', 0, 'urgent', ''), ('spam', 'spam', 1, '', ''),
            ('category-spam', 'inbox', 1, '', 'spam'), ('trash', 'trash', 1, '', ''),
            ('archive', 'archive', 1, '', ''), ('sent', 'sent', 1, '', '')]
    with main.db() as con:
        for identifier, folder, unread, label, category in rows:
            con.execute('''INSERT INTO client_mail(id,user_id,sender_name,sender_email,recipient,subject,content,folder,unread,label,category,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (identifier, user_id, 'Test', 'sender@example.com', 'me@example.com', 'Test', 'Treść', folder, unread, label, category, main.now()))
    response = client.get('/api/client-mail/summary')
    assert response.status_code == 200
    assert response.json() == {'total': 3, 'unread': 2, 'urgent': 1, 'today': 3, 'today_unread': 2, 'today_urgent': 1,
                               'today_clients': 0, 'today_government': 0, 'today_other': 3, 'today_invoices': 0}
    with main.db() as con:
        assert con.execute("SELECT unread FROM client_mail WHERE id='new'").fetchone()['unread'] == 1
    create_reader(client); login(client, READER)
    assert client.get('/api/client-mail/summary').json() == empty_summary()
    client.post('/api/logout')
    assert client.get('/api/client-mail/summary').status_code == 401


def test_summary_empty_mailbox_returns_zeros(app_client):
    _, client = app_client
    assert client.get('/api/client-mail/summary').json() == empty_summary()


def empty_summary():
    return dict.fromkeys(('total', 'unread', 'urgent', 'today', 'today_unread', 'today_urgent',
                          'today_clients', 'today_government', 'today_other', 'today_invoices'), 0)


def test_today_counts_polish_calendar_day_separately_from_all_unread(app_client, monkeypatch):
    main, client = app_client
    monkeypatch.setattr(mail_sync, 'utc_now', lambda: datetime(2026, 10, 16, 12, tzinfo=timezone.utc))
    user_id = client.get('/api/me').json()['id']
    stamps = [('yesterday', '2026-10-15T21:59:59+00:00', 1),
              ('midnight', '2026-10-15T22:00:00+00:00', 1),
              ('read-today', '2026-10-16T09:00:00+02:00', 0),
              ('today', '2026-10-16T10:00:00+00:00', 1),
              ('tomorrow', '2026-10-16T22:00:00+00:00', 1)]
    with main.db() as con:
        for identifier, stamp, unread in stamps:
            con.execute('''INSERT INTO client_mail(id,user_id,sender_name,sender_email,recipient,subject,content,folder,unread,created_at)
                VALUES(?,?,?,?,?,?,?,'inbox',?,?)''', (identifier, user_id, 'Test', 'sender@example.com',
                'me@example.com', 'Test', 'Test', unread, stamp))
    assert client.get('/api/client-mail/summary').json() == {
        'total': 5, 'unread': 4, 'urgent': 0, 'today': 3, 'today_unread': 2, 'today_urgent': 0,
        'today_clients': 0, 'today_government': 0, 'today_other': 3, 'today_invoices': 0}


def test_today_breakdown_respects_company_rules_government_and_counts_invoice_once(app_client):
    from backend.test_client_mail import imported
    from backend.test_mail_rules import assign
    main, client = app_client
    company = imported(client)
    assert assign(client, company, scope='domain').status_code == 200
    user_id = company['user_id']
    with main.db() as con:
        for identifier, sender, label, category, folder in [
            ('company-invoice', 'billing@example.com', 'invoice', 'invoice', 'inbox'),
            ('government', 'info@urzad.gov.pl', '', '', 'inbox'),
            ('other', 'person@other.example', '', 'invoice', 'inbox'),
            ('spam', 'spam@other.example', 'invoice', 'invoice', 'spam')]:
            con.execute('''INSERT INTO client_mail(id,user_id,sender_name,sender_email,recipient,subject,content,folder,label,category,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (identifier, user_id, 'Test', sender, 'me@example.com',
                'Test', 'Test', folder, label, category, main.now()))
    data = client.get('/api/client-mail/summary').json()
    assert data['today'] == 4
    assert data['today_clients'] == 2
    assert data['today_government'] == 1
    assert data['today_other'] == 1
    assert data['today_invoices'] == 2
    assert sum(data[k] for k in ('today_clients', 'today_government', 'today_other')) == data['today']
