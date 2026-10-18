from backend.test_storage import app_client
from backend.test_task_notifications import mail_task
from backend.test_access import ADMIN, READER, create_account, login


def test_email_source_preview_for_task_participants_without_mailbox_access(app_client):
    main, client = app_client
    owner, reader, task = mail_task(main, client)
    url = '/api/tasks/' + task['id'] + '/source'
    source = client.get(url).json()
    assert source['channel'] == 'email' and source['content'] == 'Please check'
    assert source['mail'] == {'id': 'source', 'folder': 'inbox'}
    assert task['source_message']['available'] is True
    assert task['source_message']['title'] == 'Request'
    assert task['client'] == {'name': 'Client', 'email': 'client@example.com', 'company': ''}
    login(client, READER)
    mine = client.get('/api/tasks').json()['mine'][0]
    assert mine['source_message']['available'] is True
    assert 'source_mail_id' not in mine
    assert mine['client']['email'] == 'client@example.com'
    assert mine['sender_name'] != mine['client']['email']
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert response.json()['content'] == 'Please check' and response.json()['mail'] is None
    assert client.get('/api/client-mail').json() == []
    assert set(response.json()) == {'source', 'channel', 'title', 'sender', 'sender_email', 'recipient', 'content', 'created_at', 'mail'}
    login(client, ADMIN)
    create_account(client, name='outsider', password='outsider-password-123', role='user')
    login(client, {'name': 'outsider', 'password': 'outsider-password-123'})
    assert client.get(url).status_code == 404
    client.post('/api/logout')
    assert client.get(url).status_code == 401


def test_deleted_email_source_is_marked_unavailable(app_client):
    main, client = app_client
    owner, reader, task = mail_task(main, client)
    with main.db() as con:
        con.execute("DELETE FROM client_mail WHERE id='source'")
    source = client.get('/api/tasks').json()['sent'][0]['source_message']
    assert source['available'] is False and source['title'] == 'Request'
    assert client.get('/api/tasks/' + task['id'] + '/source').status_code == 404
    assert client.get('/api/tasks').json()['sent'][0]['client']['email'] == 'client@example.com'


def test_client_identification_uses_mailbox_company_assignment(app_client):
    main, client = app_client
    owner, reader, task = mail_task(main, client)
    response = client.post('/api/client-mail/source/company', json={'version': 1, 'name': 'Client Company', 'scope': 'email'})
    assert response.status_code == 200, response.text
    identity = client.get('/api/tasks').json()['sent'][0]['client']
    assert identity == {'name': 'Client', 'email': 'client@example.com', 'company': 'Client Company'}
    login(client, READER)
    assert client.get('/api/tasks').json()['mine'][0]['client'] == identity


def test_portal_source_uses_original_message_and_rejects_private_or_mixed_sources(app_client):
    main, client = app_client
    owner, reader, existing = mail_task(main, client)
    with main.db() as con:
        for identifier, recipient in [('portal', owner['id']), ('private', reader['id'])]:
            con.execute('INSERT INTO user_messages(id,sender_id,recipient_id,subject,message,created_at) VALUES(?,?,?,?,?,?)',
                        (identifier, reader['id'], recipient, 'Portal request', 'Original portal content', '2026-10-17T10:00:00Z'))
    body = {'title': 'Portal task', 'description': 'Edited task content', 'assignee_id': reader['id'], 'source_message_id': 'internal:portal'}
    result = client.post('/api/tasks', json=body)
    assert result.status_code == 201, result.text
    task = result.json()
    assert task['source_message']['channel'] == 'user'
    assert task['has_email_notifications'] is False
    login(client, READER)
    source = client.get('/api/tasks/' + task['id'] + '/source').json()
    assert source['content'] == 'Original portal content' and source['mail'] is None
    login(client, ADMIN)
    assert client.post('/api/tasks', json={**body, 'source_message_id': 'internal:private'}).status_code == 404
    assert client.post('/api/tasks', json={**body, 'source_mail_id': 'source'}).status_code == 422


def test_edelivery_source_links_to_original_register_record(app_client):
    main, client = app_client
    owner = client.get('/api/me').json()
    record = client.post('/api/edeliveries', json={'title': 'Letter', 'correspondent': 'Office',
        'reference': 'REF-1', 'direction': 'incoming', 'status': 'received', 'record_date': '2026-10-17', 'notes': 'Register notes'}).json()
    task = client.post('/api/tasks', json={'title': 'Check letter', 'assignee_id': owner['id'],
        'source_message_id': 'edelivery:' + record['id']})
    assert task.status_code == 201, task.text
    source = client.get('/api/tasks/' + task.json()['id'] + '/source').json()
    assert source['channel'] == 'edelivery' and source['title'] == 'Letter' and source['content'] == 'Register notes'
