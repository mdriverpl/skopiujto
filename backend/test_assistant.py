import json
import httpx
import pytest
from fastapi import HTTPException

from backend import assistant, ai
from backend.test_storage import app_client
from backend.test_access import READER, create_reader, login


def mocked_router(monkeypatch, action, **fields):
    async def recognize(prompt):
        return assistant.AssistantPlan(action=action, **fields)
    monkeypatch.setattr(assistant, 'recognize', recognize)


@pytest.mark.parametrize('action', ['message', 'document', 'survey', 'meeting', 'task', 'note', 'clarify'])
def test_assistant_only_prepares_the_requested_operation_without_writing(app_client, monkeypatch, action):
    main, client = app_client
    mocked_router(monkeypatch, action, title='Spotkanie zespołu', description='Sala 4',
                  due_at='2030-01-02T09:00:00+01:00', explanation='Sprawdź podgląd.')
    response = client.post('/api/ai/assistant/plan', json={'prompt': '  Moje polecenie  '})
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan['action'] == action and plan['prompt'] == 'Moje polecenie'
    if action in ('meeting', 'task'):
        assert plan['assignee_id'] == client.get('/api/me').json()['id']
        assert plan['due_at'] == '2030-01-02T08:00:00Z'
    with main.db() as con:
        for table in ('user_tasks', 'user_messages', 'documents', 'ai_command_jobs', 'notes'):
            assert con.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0


def test_meeting_without_date_asks_for_date_and_then_can_be_saved_as_own_task(app_client, monkeypatch):
    _, client = app_client
    mocked_router(monkeypatch, 'meeting', title='Spotkanie zespołu', description='Sala 4')
    plan = client.post('/api/ai/assistant/plan', json={'prompt': 'Zaplanuj spotkanie'}).json()
    assert plan['due_at'] is None and 'datę i godzinę' in plan['explanation']
    assert client.get('/api/tasks').json()['mine'] == []
    saved = client.post('/api/tasks', json={'title': plan['title'], 'description': plan['description'],
                         'assignee_id': plan['assignee_id'], 'due_at': '2030-01-02T09:00:00+01:00'})
    assert saved.status_code == 201
    listing = client.get('/api/tasks').json()
    assert listing['waiting'] == 1 and listing['mine'][0]['due_at'] == '2030-01-02T08:00:00+00:00'


def test_assistant_authentication_blank_prompt_and_failed_request_does_not_lock_user(app_client, monkeypatch):
    _, client = app_client
    assert client.post('/api/ai/assistant/plan', json={'prompt': ' '}).status_code == 422
    assert client.post('/api/ai/assistant/plan', json={'prompt': 'x' * 6001}).status_code == 422
    async def fail(prompt):
        raise HTTPException(502, 'Test error')
    monkeypatch.setattr(assistant, 'recognize', fail)
    assert client.post('/api/ai/assistant/plan', json={'prompt': 'Polecenie'}).status_code == 502
    mocked_router(monkeypatch, 'document', explanation='Przygotuję ofertę.')
    assert client.post('/api/ai/assistant/plan', json={'prompt': 'Zrób ofertę dla pracowników'}).status_code == 200
    client.post('/api/logout')
    assert client.post('/api/ai/assistant/plan', json={'prompt': 'Zrób ofertę'}).status_code == 401


def test_document_route_keeps_existing_generation_permissions(app_client, monkeypatch):
    _, client = app_client
    create_reader(client)
    login(client, READER)
    mocked_router(monkeypatch, 'document', explanation='Przygotuję ofertę.')
    route = client.post('/api/ai/assistant/plan', json={'prompt': 'Zrób dokument oferta dla pracowników'}).json()
    assert route['action'] == 'document'
    async def forbidden(*args, **kwargs):
        raise AssertionError('Unauthorized generation must not call OpenAI')
    monkeypatch.setattr(ai, 'generate', forbidden)
    assert client.post('/api/ai/generate', json={'prompt': route['prompt'], 'kind': 'document'}).status_code == 403


@pytest.mark.parametrize('payload', [
    {'action': 'meeting', 'title': 'Spotkanie', 'description': '', 'due_at': '2030-01-01T10:00:00', 'explanation': ''},
    {'action': 'delete', 'title': '', 'description': '', 'due_at': None, 'explanation': ''},
    {'action': 'meeting', 'title': 'x' * 201, 'description': '', 'due_at': None, 'explanation': ''},
])
def test_invalid_provider_plan_is_rejected(app_client, monkeypatch, payload):
    _, client = app_client
    monkeypatch.setattr(ai, 'settings', lambda: {'key': 'test-key', 'model': 'configured-model'})
    def handle(request):
        return httpx.Response(200, json={'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(payload)}]}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(assistant.httpx, 'AsyncClient', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)))
    assert client.post('/api/ai/assistant/plan', json={'prompt': 'Zaplanuj spotkanie'}).status_code == 502


def test_provider_has_operation_schema_date_context_and_configured_model(app_client, monkeypatch):
    _, client = app_client
    monkeypatch.setattr(ai, 'settings', lambda: {'key': 'test-key', 'model': 'configured-model'})
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        plan = {'action': 'document', 'title': '', 'description': '', 'due_at': None, 'explanation': 'Przygotuję ofertę.'}
        return httpx.Response(200, json={'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(plan)}]}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(assistant.httpx, 'AsyncClient', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)))
    result = client.post('/api/ai/assistant/plan', json={'prompt': 'Zrób dokument oferta dla naszych pracowników'})
    assert result.status_code == 200 and result.json()['action'] == 'document'
    request = requests[0]
    assert request['model'] == 'configured-model' and request['store'] is False
    assert request['text']['format']['strict'] is True
    assert set(request['text']['format']['schema']['properties']['action']['enum']) == {'message', 'document', 'survey', 'meeting', 'task', 'note', 'clarify'}
    context = json.loads(request['input'])
    assert context['time_zone'] == 'Europe/Warsaw' and context['current_datetime']
    assert set(context) == {'command', 'current_datetime', 'time_zone'}