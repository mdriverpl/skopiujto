import pytest
from fastapi import HTTPException

from backend import mailer, mail_settings
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login


def mail_task(main, client):
    owner = client.get('/api/me').json()
    reader = create_reader(client)
    with main.db() as con:
        con.execute('''INSERT INTO client_mail(id,user_id,sender_name,sender_email,recipient,subject,content,folder,created_at)
            VALUES(?,?,?,?,?,?,?,'inbox',?)''', ('source', owner['id'], 'Client', 'client@example.com',
            'office@example.com', 'Request', 'Please check', '2026-10-17T10:00:00Z'))
    response = client.post('/api/tasks', json={'title': 'Check request', 'description': 'Details',
        'assignee_id': reader['id'], 'source_mail_id': 'source', 'due_at': '2030-01-02T10:00:00Z'})
    assert response.status_code == 201, response.text
    return owner, reader, response.json()


@pytest.fixture
def transport(monkeypatch):
    sent, accounts = [], []
    def configuration(con, current):
        accounts.append(current['id'])
        return {'sender': 'office@example.com'}, 'Office'
    monkeypatch.setattr(mail_settings, 'smtp_config', configuration)
    monkeypatch.setattr(mailer, 'send_message', lambda *args: sent.append(args))
    return sent, accounts


def test_status_changes_email_original_sender_from_task_authors_mailbox_and_notify_portal(app_client, transport):
    main, client = app_client
    owner, reader, task = mail_task(main, client)
    main.initialize()
    login(client, READER)
    url = '/api/tasks/' + task['id'] + '/status'
    for status, version in [('in_progress', 1), ('done', 2)]:
        response = client.patch(url, json={'status': status, 'version': version})
        assert response.status_code == 200, response.text
        assert response.json()['notification']['status'] == 'sent'
    sent, accounts = transport
    assert len(sent) == 2 and accounts == [owner['id'], owner['id']]
    assert all(message[1] == 'client@example.com' for message in sent)
    assert all(message[3] == 'Re: Request' for message in sent)
    assert 'W toku' in sent[0][4] and 'Wykonano' in sent[1][4]
    assert client.patch(url, json={'status': 'done', 'version': 2}).status_code == 409
    assert client.patch(url, json={'status': 'done', 'version': 3}).status_code == 200
    assert len(sent) == 2
    login(client, ADMIN)
    messages = client.get('/api/messages').json()
    assert len(messages) == 2 and all(not message['read_at'] for message in messages)
    confirmations = [item for item in client.get('/api/client-mail').json() if item['folder'] == 'sent']
    assert len(confirmations) == 2 and all(item['sender_email'] == 'office@example.com' for item in confirmations)


def test_failed_smtp_keeps_updated_status_and_one_retryable_draft(app_client, transport, monkeypatch):
    main, client = app_client
    owner, reader, task = mail_task(main, client)
    def fail(*args):
        raise HTTPException(503, 'SMTP unavailable')
    monkeypatch.setattr(mailer, 'send_message', fail)
    login(client, READER)
    response = client.patch('/api/tasks/' + task['id'] + '/status', json={'status': 'in_progress', 'version': 1})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'in_progress' and response.json()['version'] == 2
    assert response.json()['notification'] == {'status': 'failed', 'message': 'SMTP unavailable'}
    assert client.get('/api/tasks').json()['mine'][0]['status'] == 'in_progress'
    login(client, ADMIN)
    drafts = [item for item in client.get('/api/client-mail').json() if item['folder'] == 'drafts']
    assert len(drafts) == 1 and drafts[0]['recipient'] == 'client@example.com'
    monkeypatch.setattr(mailer, 'send_message', lambda *args: transport[0].append(args))
    result = client.post('/api/client-mail/' + drafts[0]['id'] + '/send', json={'version': drafts[0]['version']})
    assert result.status_code == 200 and result.json()['folder'] == 'sent'


def test_mail_source_cannot_be_another_accounts_or_spam(app_client):
    main, client = app_client
    owner, reader, task = mail_task(main, client)
    body = {'title': 'Invalid source', 'assignee_id': reader['id'], 'source_mail_id': 'source'}
    login(client, READER)
    assert client.post('/api/tasks', json=body).status_code == 404
    login(client, ADMIN)
    with main.db() as con:
        con.execute("UPDATE client_mail SET folder='spam' WHERE id='source'")
    assert client.post('/api/tasks', json=body).status_code == 422
    with main.db() as con:
        con.execute("UPDATE client_mail SET folder='inbox',category='spam' WHERE id='source'")
    assert client.post('/api/tasks', json=body).status_code == 422


def test_cancellation_notifies_original_sender_and_uses_persisted_recipient(app_client, transport):
    main, client = app_client
    owner, reader, task = mail_task(main, client)
    with main.db() as con:
        con.execute("DELETE FROM client_mail WHERE id='source'")
    response = client.patch('/api/tasks/' + task['id'] + '/status', json={'status': 'cancelled', 'version': 1})
    assert response.status_code == 200, response.text
    assert response.json()['notification']['status'] == 'sent'
    assert transport[0][0][1] == 'client@example.com'
    assert 'Anulowano' in transport[0][0][4]
    login(client, READER)
    assert len(client.get('/api/messages').json()) == 1


def test_unlinked_task_notifies_participant_without_sending_email(app_client, transport):
    main, client = app_client
    reader = create_reader(client)
    task = client.post('/api/tasks', json={'title': 'Portal task', 'assignee_id': reader['id']}).json()
    login(client, READER)
    response = client.patch('/api/tasks/' + task['id'] + '/status', json={'status': 'done', 'version': 1})
    assert response.status_code == 200, response.text
    assert 'notification' not in response.json()
    assert not transport[0]
    login(client, ADMIN)
    assert len(client.get('/api/messages').json()) == 1
