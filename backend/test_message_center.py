import json

from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login


def seed(main, client):
    owner = client.get('/api/me').json()
    reader = create_reader(client)
    timestamp = '2026-10-17T10:00:00Z'
    with main.db() as con:
        for identifier, user_id, folder in [('mail', owner['id'], 'inbox'), ('sent', owner['id'], 'sent'), ('hidden', reader['id'], 'inbox')]:
            con.execute('''INSERT INTO client_mail(id,user_id,sender_name,sender_email,recipient,subject,content,folder,unread,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)''', (identifier,user_id,'Nadawca','sender@example.com','recipient@example.com',
                'Zażółć gęślą jaźń', 'Treść e-maila',folder,1,timestamp))
        for identifier, sender, recipient in [('out',owner['id'],reader['id']), ('in',reader['id'],owner['id']), ('private',reader['id'],reader['id'])]:
            con.execute('INSERT INTO user_messages(id,sender_id,recipient_id,subject,message,created_at) VALUES(?,?,?,?,?,?)',
                        (identifier,sender,recipient,'Spotkanie','Treść dla pracownika',timestamp))
        payload = {'subject':'Powiadomienie', 'message':'Treść SMS', 'recipients':[
            {'id':'u:reader','name':'Pracownik','channel':'user','status':'sent','address':reader['id']},
            {'id':'d:sms','name':'Kontakt SMS','channel':'sms','status':'sent','address':'+48600123456','sent_at':timestamp},
            {'id':'d:email','name':'Kontakt e-mail','channel':'email','status':'failed','address':'contact@example.com','reason':'Brak połączenia'},
            {'id':'d:skip','name':'Pominięty','channel':'sms','status':'skipped','address':'+48600654321'}]}
        for identifier, user_id in [('job',owner['id']), ('private-job',reader['id'])]:
            con.execute('INSERT INTO ai_command_jobs(id,user_id,prompt,payload,status,created_at,expires) VALUES(?,?,?,?,?,?,?)',
                        (identifier,user_id,'',json.dumps(payload),'completed',timestamp,20000000000))
    response = client.post('/api/edeliveries', json={'title':'Pismo z urzędu','correspondent':'Urząd',
        'reference':'REF-1','direction':'incoming','status':'received','record_date':'2026-10-16','notes':'Notatka w rejestrze'})
    assert response.status_code == 201, response.text
    return owner, reader


def test_combines_all_channels_both_directions_without_duplicate_internal_dispatches(app_client):
    main, client = app_client
    _, reader = seed(main, client)
    response = client.get('/api/message-center')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['counts'] == {'email':3,'user':2,'sms':1,'edelivery':1}
    assert data['total'] == 7 and data['unread'] == 3
    assert {item['direction'] for item in data['items']} == {'incoming','outgoing'}
    assert not any(item['id'].startswith('dispatch:job:u:') for item in data['items'])
    assert not any('hidden' in item['id'] or 'private' in item['id'] for item in data['items'])
    sms = next(item for item in data['items'] if item['channel'] == 'sms')
    assert sms['content'] == 'Treść SMS' and sms['recipient'] == 'Kontakt SMS'
    assert data['items'][-1]['source'] == 'edelivery'
    assert next(item for item in data['items'] if item['id'] == 'email:mail')['folder'] == 'inbox'
    assert next(item for item in data['items'] if item['id'] == 'internal:in')['reply_to'] == {'id': 'u:' + reader['id'], 'name': reader['name']}
    assert next(item for item in data['items'] if item['id'] == 'internal:out')['reply_to'] is None


def test_spam_is_excluded_from_received_items_and_counts_but_remains_in_mailbox(app_client):
    main, client = app_client
    owner, _ = seed(main, client)
    with main.db() as con:
        for identifier, folder, category in [('spam-folder', 'spam', ''), ('spam-category', 'inbox', 'spam')]:
            con.execute('''INSERT INTO client_mail(id,user_id,sender_name,sender_email,recipient,subject,content,folder,category,unread,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (identifier, owner['id'], 'Sender', 'spam@example.com', 'me@example.com',
                'Spam', 'Unwanted message', folder, category, 1, '2026-10-17T10:00:00Z'))
    data = client.get('/api/message-center').json()
    assert data['total'] == 7 and data['unread'] == 3
    assert data['counts']['email'] == 3
    assert not any(item['id'].startswith('email:spam-') for item in data['items'])
    native = client.get('/api/client-mail').json()
    assert {'spam-folder', 'spam-category'} <= {item['id'] for item in native}
    assert next(item for item in native if item['id'] == 'spam-folder')['folder'] == 'spam'


def test_read_state_persists_and_internal_status_matches_portal(app_client):
    main, client = app_client
    seed(main, client)
    items = client.get('/api/message-center', params={'direction': 'incoming'}).json()['items']
    delivery = next(item for item in items if item['source'] == 'edelivery')
    assert delivery['unread'] is True
    for identifier in ('internal:in', delivery['id']):
        path = '/api/message-center/' + identifier + '/read-state'
        for unread in (False, True, False):
            response = client.patch(path, json={'unread': unread})
            assert response.status_code == 200, response.text
            reloaded = client.get('/api/message-center').json()['items']
            assert next(item for item in reloaded if item['id'] == identifier)['unread'] is unread
            if identifier == 'internal:in':
                portal = client.get('/api/messages').json()
                assert bool(next(item for item in portal if item['id'] == 'in')['read_at']) is not unread
    assert client.get('/api/message-center').json()['unread'] == 1
    client.patch('/api/message-center/internal:in/read-state', json={'unread': True})
    assert client.post('/api/messages/in/read').status_code == 200
    assert next(item for item in client.get('/api/message-center').json()['items'] if item['id'] == 'internal:in')['unread'] is False


def test_read_state_cannot_change_other_users_or_outgoing_messages(app_client):
    main, client = app_client
    seed(main, client)
    for identifier in ('internal:out', 'internal:private', 'missing:one'):
        assert client.patch('/api/message-center/' + identifier + '/read-state', json={'unread': False}).status_code == 404
    assert client.patch('/api/message-center/internal:in/read-state', json={'unread': 'no'}).status_code == 422
    client.post('/api/logout')
    assert client.patch('/api/message-center/internal:in/read-state', json={'unread': False}).status_code == 401


def test_filters_pagination_and_account_isolation(app_client):
    main, client = app_client
    seed(main, client)
    filtered = client.get('/api/message-center', params={'channel':'email','direction':'incoming','search':'ZAŻÓŁĆ'}).json()
    assert filtered['total'] == 1 and filtered['items'][0]['id'] == 'email:mail'
    pages = [client.get('/api/message-center', params={'offset':offset,'limit':2}).json()['items'] for offset in range(0,8,2)]
    assert len({item['id'] for page in pages for item in page}) == 7
    login(client, READER)
    reader_data = client.get('/api/message-center').json()
    assert 'email:hidden' in {item['id'] for item in reader_data['items']}
    assert not any(item['id'] in ('email:mail','email:sent') or item['id'].startswith('dispatch:job:') or item['source'] == 'edelivery'
                   for item in reader_data['items'])
    client.post('/api/logout')
    assert client.get('/api/message-center').status_code == 401


def test_file_delivery_sms_and_employee_approvals_use_channel_and_do_not_expose_tokens(app_client):
    main, client = app_client
    owner = client.get('/api/me').json()
    reader = create_reader(client)
    doc = client.post('/api/files', files={'file':('Umowa.pdf',b'file-content')}).json()
    with main.db() as con:
        con.execute('''INSERT INTO file_mailings(id,document_id,sender_id,sender_name,title,filename,version,file_size,sha256,message,created_at,expires)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', ('mailing',doc['id'],owner['id'],owner['name'],'Umowa','Umowa.pdf',1,12,'a'*64,'Proszę o akceptację','2026-10-17T10:00:00Z',20000000000))
        for identifier, channel, target in [('sms','sms',None), ('employee','user',reader['id'])]:
            con.execute('''INSERT INTO file_mail_recipients(id,mailing_id,email,name,token_hash,channel,phone,user_id,delivery_status)
                VALUES(?,?,?,?,?,?,?,?,?)''', (identifier,'mailing','','Odbiorca','secret-'+identifier,channel,'+48600123456' if channel == 'sms' else '',target,'sent'))
    data = client.get('/api/message-center').json()
    assert data['counts'] == {'sms':1,'user':1}
    assert all(item['source'] == 'approval' and item['filename'] == 'Umowa.pdf' for item in data['items'])
    assert 'secret-' not in json.dumps(data) and 'token_hash' not in json.dumps(data) and 'file-content' not in json.dumps(data)
    login(client, READER)
    incoming = client.get('/api/message-center').json()
    assert incoming['total'] == 1 and incoming['items'][0]['channel'] == 'user'
    assert incoming['items'][0]['direction'] == 'incoming'


def test_message_center_is_not_limited_to_legacy_inbox_history_limits(app_client):
    main, client = app_client
    owner = client.get('/api/me').json()
    with main.db() as con:
        for number in range(105):
            con.execute('INSERT INTO user_messages(id,sender_id,recipient_id,subject,message,created_at) VALUES(?,?,?,?,?,?)',
                        (f'message-{number}',owner['id'],owner['id'],'Notatka','Treść','2026-10-17T10:00:00Z'))
    data = client.get('/api/message-center',params={'offset':100,'limit':40}).json()
    assert data['total'] == 105 and len(data['items']) == 5
    for params in ({'limit':101},{'offset':-1},{'channel':'unknown'},{'direction':'unknown'}):
        assert client.get('/api/message-center',params=params).status_code == 422
