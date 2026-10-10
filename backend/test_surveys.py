import pytest
from backend import surveys
from backend import mailer, sms
from fastapi import HTTPException
import re
import time
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, create_account, login

def payload(recipients):
    return {'title': 'Termin spotkania', 'description': 'Wybierz termin.', 'recipients': recipients,
            'questions': [
                {'id': 'name', 'label': 'Imię', 'type': 'text'},
                {'id': 'choice', 'label': 'Termin', 'type': 'select', 'options': ['Poniedziałek', 'Wtorek']},
                {'id': 'count', 'label': 'Liczba osób', 'type': 'number', 'required': False},
                {'id': 'day', 'label': 'Data', 'type': 'date', 'required': False},
                {'id': 'yes', 'label': 'Potwierdzenie', 'type': 'checkbox', 'required': False},
            ]}

@pytest.mark.parametrize('closed', [False, True])
def test_delete_survey_owner_only_removes_answers_invites_and_reports(app_client, monkeypatch, closed):
    main, client = app_client
    reader = create_reader(client)
    identifier = client.post('/api/surveys', json=payload([reader['id']])).json()['id']
    retained = client.post('/api/surveys', json=payload([])).json()['id']
    messages = []
    monkeypatch.setattr(mailer, 'configuration', lambda: {'public_url': 'https://app.example.com'})
    monkeypatch.setattr(mailer, 'send_message', lambda *args: messages.append(args))
    sent = client.post(f'/api/surveys/{identifier}/send', json={
        'request_id': 'delete_test_request_123', 'recipients': [{'channel': 'email', 'address': 'anna@example.com'}]})
    assert sent.status_code == 200, sent.text
    token = re.search(r'/survey/([A-Za-z0-9_-]+)', messages[0][-1]).group(1)
    answer = {'answers': {'name': 'Anna', 'choice': 'Wtorek'}}
    assert client.post(f'/api/survey-links/{token}/responses', json=answer).status_code == 200
    login(client, READER)
    assert client.post(f'/api/surveys/{identifier}/responses', json=answer).status_code == 200
    assert client.delete(f'/api/surveys/{identifier}').status_code == 403
    assert client.delete(f'/api/surveys/{retained}').status_code == 404
    client.post('/api/logout')
    assert client.delete(f'/api/surveys/{identifier}').status_code == 401
    login(client, ADMIN)
    with main.db() as con:
        con.execute('INSERT INTO survey_interpretations(survey_id,data,fingerprint,created_at) VALUES(?,?,?,?)',
                    (identifier, '{}', 'test', main.now()))
    if closed: assert client.post(f'/api/surveys/{identifier}/close').status_code == 200
    assert client.delete(f'/api/surveys/{identifier}').status_code == 200
    assert client.delete(f'/api/surveys/{identifier}').status_code == 404
    assert client.get(f'/api/surveys/{identifier}').status_code == 404
    assert client.get(f'/api/surveys/{retained}').status_code == 200
    assert client.get(f'/api/survey-links/{token}').status_code == 404
    assert client.post(f'/api/survey-links/{token}/responses', json=answer).status_code == 404
    with main.db() as con:
        for table in ('survey_recipients', 'survey_invites', 'survey_dispatches', 'survey_interpretations'):
            assert con.execute(f'SELECT count(*) FROM {table} WHERE survey_id=?', (identifier,)).fetchone()[0] == 0
    login(client, READER)
    assert client.get('/api/surveys').json() == []

def test_survey_assignment_response_privacy_counts_and_persistence(app_client):
    main, client = app_client
    author = client.get('/api/me').json()
    reader = create_reader(client)
    outsider = create_account(client, **{'name': 'other', 'password': 'other-password-123'})
    result = client.post('/api/surveys', json=payload([reader['id'], author['id'], reader['id']]))
    assert result.status_code == 201, result.text
    item = result.json(); identifier = item['id']
    assert item['expected'] == 2 and item['completed'] == 0
    assert client.post(f'/api/surveys/{identifier}/responses', json={'answers': {'name': 'Autor', 'choice': 'Wtorek'}}).status_code == 200
    login(client, READER)
    assert client.get('/api/surveys').json()[0]['completed'] == 1
    assert any('Ankieta:' in message['subject'] for message in client.get('/api/messages').json())
    details = client.get('/api/surveys/' + identifier).json()
    assert len(details['responses']) == 1 and details['responses'][0]['is_me']
    assert details['responses'][0]['answers'] is None
    assert details['responses'][0]['sent_at'] == details['created_at']
    assert client.post(f'/api/surveys/{identifier}/close').status_code == 403
    response = {'answers': {'name': 'Jan', 'choice': 'Poniedziałek', 'count': '2.5', 'day': '2030-01-01', 'yes': False}}
    assert client.post(f'/api/surveys/{identifier}/responses', json=response).status_code == 200
    assert client.post(f'/api/surveys/{identifier}/responses', json=response).status_code == 409
    assert client.get('/api/surveys').json()[0]['completed'] == 2
    login(client, {'name': 'other', 'password': 'other-password-123'})
    assert client.get('/api/surveys').json() == []
    assert client.get('/api/surveys/' + identifier).status_code == 404
    assert client.post(f'/api/surveys/{identifier}/responses', json=response).status_code == 404
    login(client, ADMIN)
    main.initialize()
    details = client.get('/api/surveys/' + identifier).json()
    assert len(details['responses']) == 2 and details['completed'] == 2
    assert next(p for p in details['responses'] if p['user_id'] == reader['id'])['answers']['count'] == '2.5'
    assert next(p for p in details['responses'] if p['is_me'])['answers']['name'] == 'Autor'
    assert client.post('/api/surveys/' + identifier + '/close').json()['closed_at']

def test_invalid_recipients_and_questions_are_atomic_and_owner_cannot_answer_unassigned(app_client):
    main, client = app_client
    reader = create_reader(client)
    assert client.post('/api/surveys', json=payload([reader['id'], 'missing'])).status_code == 422
    with main.db() as con:
        assert con.execute('SELECT count(*) FROM surveys').fetchone()[0] == 0
        assert con.execute('SELECT count(*) FROM user_messages').fetchone()[0] == 0
    invalid = payload([reader['id']]); invalid['questions'].append(invalid['questions'][0])
    assert client.post('/api/surveys', json=invalid).status_code == 422
    invalid = payload([reader['id']]); invalid['questions'][1]['options'] = ['Same', 'Same']
    assert client.post('/api/surveys', json=invalid).status_code == 422
    identifier = client.post('/api/surveys', json=payload([reader['id']])).json()['id']
    assert client.post(f'/api/surveys/{identifier}/responses', json={'answers': {'name': 'Jan', 'choice': 'Wtorek'}}).status_code == 403
    assert client.post(f'/api/surveys/{identifier}/close').status_code == 200
    login(client, READER)
    assert client.post(f'/api/surveys/{identifier}/responses', json={'answers': {'name': 'Jan', 'choice': 'Wtorek'}}).status_code == 409
    client.post('/api/logout')
    assert client.get('/api/surveys').status_code == 401
    assert client.get('/api/surveys/recipients').status_code == 401

@pytest.mark.parametrize('extra', [{'name': ''}, {'choice': 'Spoza listy'}, {'count': 'nan'}, {'count': 'inf'}, {'day': '2030-02-30'}, {'yes': 'false'}, {'unknown': 'value'}])
def test_invalid_answers_do_not_increment_counts(app_client, extra):
    _, client = app_client
    author = client.get('/api/me').json()
    identifier = client.post('/api/surveys', json=payload([author['id']])).json()['id']
    response = client.post(f'/api/surveys/{identifier}/responses', json={'answers': {'name': 'Anna', 'choice': 'Wtorek', **extra}})
    assert response.status_code == 422
    assert client.get('/api/surveys/' + identifier).json()['completed'] == 0

def test_required_checkbox_and_inactive_recipient(app_client):
    _, client = app_client
    reader = create_reader(client)
    client.patch('/api/admin/users/' + reader['id'], json={'active': False})
    assert all(p['id'] != reader['id'] for p in client.get('/api/surveys/recipients').json())
    assert client.post('/api/surveys', json=payload([reader['id']])).status_code == 422
    author = client.get('/api/me').json()
    body = payload([author['id']]); body['questions'][-1]['required'] = True
    identifier = client.post('/api/surveys', json=body).json()['id']
    assert client.post(f'/api/surveys/{identifier}/responses', json={'answers': {'name': 'A', 'choice': 'Wtorek'}}).status_code == 422
    assert client.post(f'/api/surveys/{identifier}/responses', json={'answers': {'name': 'A', 'choice': 'Wtorek', 'yes': True}}).status_code == 200

def test_draft_and_external_dispatch_token_answers_idempotency_privacy(app_client, monkeypatch):
    main, client = app_client
    calls = []
    monkeypatch.setattr(mailer, 'configuration', lambda: {'public_url': 'https://app.example.com'})
    monkeypatch.setattr(sms, 'configuration', lambda: {'public_url': 'https://app.example.com'})
    monkeypatch.setattr(mailer, 'send_message', lambda *args: calls.append(('email', args)))
    monkeypatch.setattr(sms, 'send_text', lambda *args: calls.append(('sms', args)))
    body = payload([]); body.pop('recipients')
    result = client.post('/api/surveys', json=body)
    assert result.status_code == 201 and result.json()['expected'] == 0
    identifier = result.json()['id']
    request = {'request_id': 'unique_request_1234', 'recipients': [
        {'channel': 'email', 'address': 'anna@example.com', 'name': 'Anna'},
        {'channel': 'email', 'address': 'anna@example.com', 'name': 'Duplicate'},
        {'channel': 'sms', 'address': '600123456', 'name': 'Jan'}]}
    sent = client.post(f'/api/surveys/{identifier}/send', json=request)
    assert sent.status_code == 200, sent.text
    assert len(sent.json()['recipients']) == 2 and len(calls) == 2
    assert client.post(f'/api/surveys/{identifier}/send', json=request).status_code == 200 and len(calls) == 2
    assert client.post(f'/api/surveys/{identifier}/send', json={**request, 'request_id': 'another_request_123'}).status_code == 409
    tokens = [re.search(r'/survey/([A-Za-z0-9_-]+)', args[-1]).group(1) for _, args in calls]
    assert client.get('/api/surveys/' + identifier).json()['expected'] == 2
    client.post('/api/logout')
    preview = client.get('/api/survey-links/' + tokens[0]).json()
    assert preview['title'] == body['title'] and 'responses' not in preview and 'address' not in preview
    response = {'answers': {'name': 'Anna', 'choice': 'Wtorek'}}
    assert client.post('/api/survey-links/' + tokens[0] + '/responses', json=response).status_code == 200
    assert client.post('/api/survey-links/' + tokens[0] + '/responses', json=response).status_code == 409
    assert client.get('/api/survey-links/' + tokens[1]).json()['answers'] is None
    assert client.get('/api/survey-links/fake-token').status_code == 404
    login(client, ADMIN)
    details = client.get('/api/surveys/' + identifier).json()
    assert details['completed'] == 1 and len(details['responses']) == 2
    assert all(p['sent_at'] for p in details['responses'])
    assert next(p for p in details['responses'] if p['channel'] == 'email')['answers']['name'] == 'Anna'
    with main.db() as con:
        stored = con.execute('SELECT token_hash FROM survey_invites').fetchall()
        assert all(row['token_hash'] not in tokens for row in stored)
    main.initialize()
    assert client.get('/api/surveys/' + identifier).json()['completed'] == 1
    client.post('/api/surveys/' + identifier + '/close')
    assert client.post('/api/survey-links/' + tokens[1] + '/responses', json=response).status_code == 409

def test_dispatch_failure_expiry_authority_and_configuration(app_client, monkeypatch):
    main, client = app_client
    reader = create_reader(client)
    identifier = client.post('/api/surveys', json=payload([reader['id']])).json()['id']
    request = {'request_id': 'unique_request_1234', 'recipients': [{'channel': 'email', 'address': 'anna@example.com'}]}
    login(client, READER)
    assert client.post(f'/api/surveys/{identifier}/send', json=request).status_code == 403
    login(client, ADMIN)
    def unavailable(): raise HTTPException(503, 'SMTP unavailable')
    monkeypatch.setattr(mailer, 'configuration', unavailable)
    assert client.post(f'/api/surveys/{identifier}/send', json=request).status_code == 503
    assert client.get('/api/surveys/' + identifier).json()['expected'] == 1
    monkeypatch.setattr(mailer, 'configuration', lambda: {'public_url': 'https://app.example.com'})
    calls = []
    def fail(*args): calls.append(args); raise HTTPException(503, 'Refused')
    monkeypatch.setattr(mailer, 'send_message', fail)
    result = client.post(f'/api/surveys/{identifier}/send', json=request).json()
    assert result['recipients'][0]['status'] == 'failed'
    assert client.post(f'/api/surveys/{identifier}/send', json=request).status_code == 200 and len(calls) == 1
    token = re.search(r'/survey/([A-Za-z0-9_-]+)', calls[0][-1]).group(1)
    assert client.get('/api/survey-links/' + token).status_code == 404
    with main.db() as con: con.execute("UPDATE survey_invites SET status='sent',expires=?", (time.time() - 1,))
    assert client.get('/api/survey-links/' + token).status_code == 410
