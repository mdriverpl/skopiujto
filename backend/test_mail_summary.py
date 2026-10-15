from backend.test_storage import app_client
from backend.test_access import READER, create_reader, login


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
    assert response.json() == {'total': 3, 'unread': 2, 'urgent': 1}
    with main.db() as con:
        assert con.execute("SELECT unread FROM client_mail WHERE id='new'").fetchone()['unread'] == 1
    create_reader(client); login(client, READER)
    assert client.get('/api/client-mail/summary').json() == {'total': 0, 'unread': 0, 'urgent': 0}
    client.post('/api/logout')
    assert client.get('/api/client-mail/summary').status_code == 401


def test_summary_empty_mailbox_returns_zeros(app_client):
    _, client = app_client
    assert client.get('/api/client-mail/summary').json() == {'total': 0, 'unread': 0, 'urgent': 0}
