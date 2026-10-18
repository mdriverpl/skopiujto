import json
import httpx
import pytest
from fastapi import HTTPException
from backend import ai_commands, ai, mailer, sms
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login

@pytest.fixture
def transport(monkeypatch):
    calls = []
    monkeypatch.setattr(mailer, 'configuration', lambda: {'test': True})
    monkeypatch.setattr(sms, 'configuration', lambda: {'test': True})
    monkeypatch.setattr(mailer, 'send_message', lambda *args: calls.append(('email', args)))
    monkeypatch.setattr(sms, 'send_text', lambda *args: calls.append(('sms', args)))
    return calls

def mock_plan(monkeypatch, selection=None, channel='auto', action='message'):
    async def planner(body, candidates):
        chosen = candidates if selection is None else selection(candidates)
        return ai_commands.Plan(action=action, channel=channel, subject='Spotkanie', message='Spotkanie na sali o godzinie 19:00',
            recipients=[item['id'] for item in chosen], explanation='Sprawdź odbiorców.')
    monkeypatch.setattr(ai_commands, 'plan_command', planner)

def execute(client, plan, **extra):
    return client.post('/api/ai/commands/' + plan['id'] + '/execute', json={'confirmed': True,
        'subject': plan['subject'], 'message': plan['message'], 'recipients': [item['id'] for item in plan['recipients'] if item['available']], **extra})

def employee(client, email='anna@example.com'):
    dictionary = client.post('/api/dictionaries', json={'name': 'Pracownicy', 'fields': ['Imię', 'Nazwisko', 'Stanowisko', 'Email', 'Telefon']}).json()
    entry = client.post('/api/dictionaries/' + dictionary['id'] + '/entries', json={
        'values': {'Imię': 'Anna', 'Nazwisko': 'Kowalska', 'Stanowisko': 'Prawnik', 'Email': email, 'Telefon': '+48600123456'}}).json()
    return dictionary, entry


def test_dictionary_email_uses_personal_smtp_and_enforces_selected_dictionary(app_client, monkeypatch, transport):
    from cryptography.fernet import Fernet
    from backend.test_mail_settings import account
    monkeypatch.setenv('EDOCUMENTS_MAIL_SETTINGS_KEY', Fernet.generate_key().decode())
    main, client = app_client
    saved = client.put('/api/client-mail/settings', json=account())
    assert saved.status_code == 200, saved.text
    dictionary, entry = employee(client)
    other = client.post('/api/dictionaries', json={'name': 'Other contacts', 'fields': ['Email']}).json()
    contact = client.post('/api/dictionaries/' + other['id'] + '/entries', json={'values': {'Email': 'other@example.com'}}).json()
    options = client.get('/api/ai/commands/options').json()
    assert options['channels']['email']['configured'] is True
    assert options['channels']['email']['source'] == 'personal'
    body = {'subject': 'Notice', 'message': 'Details', 'channel': 'email', 'source': 'dictionaries',
            'dictionary_id': dictionary['id'], 'recipients': ['d:' + entry['id']]}
    assert client.post('/api/messages/prepare', json={**body, 'recipients': ['d:' + contact['id']]}).status_code == 422
    prepared = client.post('/api/messages/prepare', json=body)
    assert prepared.status_code == 200, prepared.text
    sent = execute(client, prepared.json())
    assert sent.status_code == 200, sent.text
    email = transport[-1][1]
    assert email[0]['sender'] == 'jan@example.com' and email[0]['host'] == 'smtp.example.com'
    assert email[1] == 'anna@example.com' and email[2] == 'Jan Kowalski'


def test_direct_email_without_dictionary_is_validated_and_sent_once(app_client, transport):
    main, client = app_client
    body = {'subject': 'Notice', 'message': 'Message body', 'channel': 'email', 'source': 'dictionaries',
            'recipients': [], 'direct_email': 'new-client@example.com'}
    response = client.post('/api/messages/prepare', json=body)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert len(plan['recipients']) == 1 and plan['recipients'][0]['address'] == body['direct_email']
    assert execute(client, plan).status_code == 200
    assert transport[0][1][1] == body['direct_email']
    assert execute(client, plan).status_code == 409
    for invalid in ({'direct_email': 'invalid'}, {'direct_email': None}, {'channel': 'sms'}):
        assert client.post('/api/messages/prepare', json={**body, **invalid}).status_code == 422


def test_history_contacts_are_private_exclude_spam_and_can_be_selected(app_client, transport):
    main, client = app_client
    owner = client.get('/api/me').json()
    reader = create_reader(client)
    with main.db() as con:
        for identifier, user_id, folder, category, sender in [
            ('history', owner['id'], 'inbox', '', 'client@example.com'),
            ('duplicate', owner['id'], 'archive', '', 'client@example.com'),
            ('spam-history', owner['id'], 'spam', '', 'spam@example.com'),
            ('classified-history', owner['id'], 'inbox', 'spam', 'classified@example.com'),
            ('private-history', reader['id'], 'inbox', '', 'private@example.com')]:
            con.execute('''INSERT INTO client_mail(id,user_id,sender_name,sender_email,recipient,subject,content,folder,category,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)''', (identifier,user_id,'Client',sender,'me@example.com','History','Text',folder,category,'2026-10-17T10:00:00Z'))
        con.execute('INSERT INTO user_messages(id,sender_id,recipient_id,subject,message,created_at) VALUES(?,?,?,?,?,?)',
                    ('history-portal',owner['id'],reader['id'],'Portal','Text','2026-10-17T10:00:00Z'))
    response = client.get('/api/messages/contacts?source=history')
    assert response.status_code == 200, response.text
    rows = response.json()
    emails = [row for row in rows if 'email' in row['channels']]
    assert len(emails) == 1 and emails[0]['channels']['email'] == 'client@example.com'
    assert any(row['channels'].get('user') == reader['id'] for row in rows)
    plan = client.post('/api/messages/prepare', json={'subject':'Reply','message':'Details','channel':'email',
        'source':'history','recipients':[emails[0]['id']]}).json()
    assert execute(client, plan).status_code == 200
    login(client, READER)
    private_rows = client.get('/api/messages/contacts?source=history').json()
    assert not any(row['channels'].get('email') == 'client@example.com' for row in private_rows)

def test_manual_message_without_ai_and_actual_send_date(app_client, monkeypatch, transport):
    main, client = app_client
    reader = create_reader(client)
    dictionary, entry = employee(client)
    def forbidden(*args): raise AssertionError('Manual messages must not call AI')
    monkeypatch.setattr(ai_commands, 'plan_command', forbidden)
    found = client.get('/api/messages/contacts').json()
    assert any(item['id'] == 'd:' + entry['id'] and item['dictionary_id'] == dictionary['id'] for item in found)
    body = {'subject': 'Spotkanie', 'message': 'Sala 19:00', 'recipients': ['u:' + reader['id']], 'source': 'users'}
    assert client.post('/api/messages/prepare', json={**body, 'recipients': ['d:' + entry['id']]}).status_code == 422
    assert client.post('/api/messages/prepare', json={**body, 'subject': ' '}).status_code == 422
    response = client.post('/api/messages/prepare', json=body)
    assert response.status_code == 200
    plan = response.json()
    assert not transport and client.get('/api/messages').json() == []
    with main.db() as con:
        con.execute('UPDATE ai_command_jobs SET created_at=? WHERE id=?', ('2000-01-01T00:00:00Z', plan['id']))
    assert execute(client, plan).status_code == 200
    sent = client.get('/api/ai/commands/history').json()[0]
    assert sent['sent_at'] != sent['created_at'] and sent['recipients'][0]['sent_at']
    assert execute(client, plan).status_code == 409
    login(client, READER)
    assert len(client.get('/api/messages').json()) == 1
    assert all(not item['id'].startswith('d:') for item in client.get('/api/messages/contacts').json())
    assert client.get('/api/messages/contacts', params={'dictionary_id': dictionary['id']}).status_code == 404

def test_preview_does_not_send_and_internal_messages_are_private_and_one_time(app_client, monkeypatch, transport):
    main, client = app_client
    reader = create_reader(client)
    mock_plan(monkeypatch, lambda contacts: [item for item in contacts if item['id'] == 'u:' + reader['id']])
    plan = client.post('/api/ai/commands/plan', json={'prompt': 'Wyślij wiadomość do użytkownika', 'source': 'users'}).json()
    assert plan['recipients'][0]['channel'] == 'user' and not transport
    with main.db() as con: assert con.execute('SELECT count(*) FROM user_messages').fetchone()[0] == 0
    assert execute(client, plan, confirmed=False).status_code == 422
    sent = execute(client, plan)
    assert sent.status_code == 200 and sent.json()['recipients'][0]['status'] == 'sent'
    assert execute(client, plan).status_code == 409
    assert client.get('/api/messages').json() == []
    login(client, READER)
    messages = client.get('/api/messages').json()
    assert len(messages) == 1 and messages[0]['message'].endswith('19:00') and not messages[0]['read_at']
    assert execute(client, plan).status_code == 404
    assert client.get('/api/ai/commands/history').json() == []
    assert client.post('/api/messages/' + messages[0]['id'] + '/read').status_code == 200
    login(client, ADMIN)
    assert client.post('/api/messages/' + messages[0]['id'] + '/read').status_code == 404
    main.initialize()
    assert client.get('/api/ai/commands/history').json()[0]['status'] == 'completed'

def test_both_sources_email_delivery_and_contact_change_blocks_send(app_client, monkeypatch, transport):
    _, client = app_client
    reader = create_reader(client)
    dictionary, entry = employee(client)
    mock_plan(monkeypatch, lambda contacts: [item for item in contacts if item['id'] in ['u:' + reader['id'], 'd:' + entry['id']]])
    plan = client.post('/api/ai/commands/plan', json={'prompt': 'Wyślij spotkanie', 'source': 'both'}).json()
    assert {item['channel'] for item in plan['recipients']} == {'user', 'email'}
    assert execute(client, plan, recipients=['d:unknown']).status_code == 422
    assert execute(client, plan).status_code == 200
    assert len(transport) == 1 and transport[0][0] == 'email'
    another = client.post('/api/ai/commands/plan', json={'prompt': 'Wyślij spotkanie', 'source': 'both'}).json()
    client.put('/api/dictionaries/' + dictionary['id'] + '/entries/' + entry['id'], json={'version': 1, 'values': {**entry['values'], 'Email': 'other@example.com'}})
    assert execute(client, another).status_code == 409 and len(transport) == 1

def test_sms_failure_is_visible_and_not_retried(app_client, monkeypatch, transport):
    _, client = app_client
    employee(client)
    mock_plan(monkeypatch, channel='sms')
    def fail(*args): transport.append(('sms-failed', args)); raise HTTPException(503, 'Niepotwierdzony SMS')
    monkeypatch.setattr(sms, 'send_text', fail)
    plan = client.post('/api/ai/commands/plan', json={'prompt': 'Wyślij SMS', 'source': 'dictionaries'}).json()
    assert plan['recipients'][0]['channel'] == 'sms'
    result = execute(client, plan)
    assert result.status_code == 200 and result.json()['recipients'][0]['status'] == 'failed'
    assert execute(client, plan).status_code == 409 and len(transport) == 1
    assert client.get('/api/ai/commands/history').json()[0]['recipients'][0]['reason'] == 'Niepotwierdzony SMS'

def test_private_dictionary_contacts_and_inactive_accounts_not_available(app_client, monkeypatch, transport):
    _, client = app_client
    reader = create_reader(client)
    dictionary, entry = employee(client)
    mock_plan(monkeypatch)
    login(client, READER)
    assert client.post('/api/ai/commands/plan', json={'prompt': 'Send', 'source': 'dictionaries', 'dictionary_id': dictionary['id']}).status_code == 404
    login(client, ADMIN)
    mock_plan(monkeypatch, lambda contacts: [item for item in contacts if item['id'] == 'u:' + reader['id']])
    plan = client.post('/api/ai/commands/plan', json={'prompt': 'Send'}).json()
    client.patch('/api/admin/users/' + reader['id'], json={'active': False})
    assert execute(client, plan).status_code == 409 and not transport

def test_clarification_and_unknown_model_ids_cannot_create_send_job(app_client, monkeypatch, transport):
    main, client = app_client
    mock_plan(monkeypatch, action='clarify')
    result = client.post('/api/ai/commands/plan', json={'prompt': 'Zrób coś'})
    assert result.json()['action'] == 'clarify' and 'id' not in result.json()
    async def bad(*args): return ai_commands.Plan(action='message', subject='Subject', message='Text', recipients=['bad'], explanation='')
    monkeypatch.setattr(ai_commands, 'plan_command', bad)
    assert client.post('/api/ai/commands/plan', json={'prompt': 'Send'}).status_code == 502
    with main.db() as con: assert con.execute('SELECT count(*) FROM ai_command_jobs').fetchone()[0] == 0
    client.post('/api/logout')
    assert client.get('/api/messages').status_code == 401
    assert client.post('/api/ai/commands/plan', json={'prompt': 'Send'}).status_code == 401

def test_provider_schema_uses_current_model_and_excludes_contact_addresses(app_client, monkeypatch):
    _, client = app_client
    dictionary, entry = employee(client)
    monkeypatch.setattr(ai, 'settings', lambda: {'key': 'test-key', 'model': 'configured-model'})
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text',
            'text': json.dumps({'action': 'message', 'channel': 'auto', 'subject': 'Spotkanie', 'message': 'Sala 19:00', 'recipients': ['d:' + entry['id']], 'explanation': 'Plan'})}]}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(ai_commands.httpx, 'AsyncClient', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)))
    result = client.post('/api/ai/commands/plan', json={'prompt': 'Wyślij do prawników', 'source': 'dictionaries'})
    assert result.status_code == 200
    request = json.loads(calls[0].content)
    assert request['model'] == 'configured-model' and request['store'] is False
    assert request['text']['format']['strict'] is True
    assert 'anna@example.com' not in request['input'] and '+48600123456' not in request['input']
    assert 'Prawnik' in request['input']

def test_manual_sms_accepts_phone_validates_source_and_executes_once(app_client, transport):
    _, client = app_client
    body = {'subject': 'Reminder', 'message': 'Tomorrow', 'channel': 'sms', 'source': 'dictionaries', 'direct_sms': '+48600123456'}
    assert client.post('/api/messages/prepare', json={**body, 'channel': 'email'}).status_code == 422
    assert client.post('/api/messages/prepare', json={**body, 'direct_sms': 'invalid'}).status_code == 422
    response = client.post('/api/messages/prepare', json=body)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan['recipients'][0]['address'] == '+48600123456'
    assert execute(client, plan).json()['recipients'][0]['status'] == 'sent'
    assert execute(client, plan).status_code == 409
    assert len(transport) == 1 and transport[0][0] == 'sms'


def test_plain_message_smtp_format_and_refusal_without_network(monkeypatch):
    mails = []
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def send_message(self, message, **kwargs): mails.append(message); return {}
        def quit(self): pass
        def close(self): pass
    monkeypatch.setattr(mailer.smtplib, 'SMTP', SMTP)
    config = {'host': 'test', 'port': 25, 'security': 'none', 'username': '', 'sender': 'sender@example.com'}
    mailer.send_message(config, 'recipient@example.com', 'Jan', 'Spotkanie\r\n', 'Sala 19:00')
    assert mails[0]['To'] == 'recipient@example.com' and mails[0]['Subject'] == 'Spotkanie'
    assert 'Sala 19:00' in mails[0].get_content() and not list(mails[0].iter_attachments())
    monkeypatch.setattr(SMTP, 'send_message', lambda *args, **kwargs: {'recipient@example.com': (550, b'refused')})
    with pytest.raises(HTTPException): mailer.send_message(config, 'recipient@example.com', 'Jan', 'Spotkanie', 'Sala 19:00')
