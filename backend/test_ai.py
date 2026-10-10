import json

import httpx
import pytest

from backend import ai
from backend.test_storage import app_client
from backend.test_access import READER, create_reader, login, make_shared

DATA = {'title': 'Umowa AI', 'category': 'Umowy', 'description': 'Wzór współpracy', 'blocks': [
    {'type': 'heading', 'text': 'Warunki współpracy', 'items': []},
    {'type': 'paragraph', 'text': 'Strony: [nazwa firmy]\nZakres: [opis]', 'items': []},
    {'type': 'bulletList', 'text': '', 'items': ['Termin: [data]', 'Cena: [kwota]']}
]}


def output(data=DATA):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps(data)}]}]}


@pytest.fixture
def provider(monkeypatch, tmp_path):
    monkeypatch.setattr(ai, 'ENV_FILE', tmp_path / '.env')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-private-key')
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-4.1-mini')
    calls = []
    result = {'status': 200, 'json': output(), 'exception': None}
    def handle(request):
        calls.append(request)
        if result['exception']:
            raise result['exception']
        return httpx.Response(result['status'], json=result['json'])
    original = httpx.AsyncClient
    monkeypatch.setattr(ai.httpx, 'AsyncClient', lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(handle)))
    return calls, result


@pytest.mark.parametrize('kind', ['document', 'template'])
def test_generates_formatted_unsaved_draft(app_client, provider, kind):
    _, client = app_client
    calls, _ = provider
    before = client.get('/api/templates').json()
    assert client.get('/api/ai/config').json() == {'available': True, 'message': ''}
    response = client.post('/api/ai/generate', json={'prompt': 'Przygotuj umowę', 'kind': kind})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['title'] == DATA['title'] and result['status'] == 'Szkic'
    assert result['rich_content']['content'][0]['type'] == 'heading'
    assert result['rich_content']['content'][-1]['type'] == 'bulletList'
    assert '[nazwa firmy]' in result['content']
    assert 'id' not in result and 'user_id' not in result
    assert client.get('/api/templates').json() == before
    assert client.get('/api/documents').json() == []
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == 'https://api.openai.com/v1/responses'
    assert request.headers['Authorization'] == 'Bearer test-private-key'
    body = json.loads(request.content)
    assert body['store'] is False and body['max_output_tokens'] == 4000
    assert body['text']['format']['strict'] is True and body['input'] == 'Przygotuj umowę'


def test_generation_obeys_folder_and_root_permissions(app_client, provider):
    _, client = app_client
    calls, _ = provider
    reader = create_reader(client)
    _, _, child, _, _ = make_shared(client, reader, {'can_add': True})
    private = client.post('/api/folders', json={'name': 'Private'}).json()
    login(client, READER)
    body = {'prompt': 'Przygotuj dokument', 'kind': 'document'}
    assert client.post('/api/ai/generate', json=body).status_code == 403
    assert client.post('/api/ai/generate', json={**body, 'kind': 'template'}).status_code == 403
    assert client.post('/api/ai/generate', json={**body, 'folder_id': private['id']}).status_code == 404
    assert calls == []
    assert client.post('/api/ai/generate', json={**body, 'folder_id': child['id']}).status_code == 200
    assert len(calls) == 1
    client.post('/api/logout')
    assert client.post('/api/ai/generate', json=body).status_code == 401
    assert client.get('/api/ai/config').status_code == 401
    assert len(calls) == 1


def test_missing_key_and_local_configuration(app_client, provider, monkeypatch, tmp_path):
    _, client = app_client
    calls, _ = provider
    monkeypatch.delenv('OPENAI_API_KEY')
    assert not client.get('/api/ai/config').json()['available']
    assert client.post('/api/ai/generate', json={'prompt': 'Dokument'}).status_code == 503
    assert calls == []
    ai.ENV_FILE.write_text('OPENAI_API_KEY=test-private-key\n', encoding='utf-8')
    assert client.get('/api/ai/config').json()['available']
    assert 'test-private-key' not in client.get('/api/ai/config').text
    assert client.post('/api/ai/generate', json={'prompt': 'Dokument'}).status_code == 200


@pytest.mark.parametrize('status, expected', [(401, 503), (403, 503), (429, 503), (500, 502)])
def test_provider_errors_are_safe_and_do_not_save(app_client, provider, status, expected):
    _, client = app_client
    calls, result = provider
    result.update(status=status, json={'error': {'message': 'test-private-key confidential-provider-detail'}})
    response = client.post('/api/ai/generate', json={'prompt': 'Dokument'})
    assert response.status_code == expected
    assert 'test-private-key' not in response.text and 'confidential-provider-detail' not in response.text
    assert client.get('/api/documents').json() == []
    assert len(calls) == 1


@pytest.mark.parametrize('response, expected', [
    ({'status': 'incomplete', 'output': []}, 502),
    ({'status': 'completed', 'output': []}, 502),
    ({'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'refusal', 'refusal': 'No'}]}]}, 422),
    (output({**DATA, 'blocks': []}), 502),
    (output({**DATA, 'title': ' '}), 502),
    (output({**DATA, 'blocks': [{'type': 'script', 'text': 'x', 'items': []}]}), 502),
])
def test_invalid_and_refused_output_does_not_create_content(app_client, provider, response, expected):
    _, client = app_client
    _, result = provider
    result['json'] = response
    assert client.post('/api/ai/generate', json={'prompt': 'Dokument'}).status_code == expected
    assert client.get('/api/documents').json() == []


def test_timeout_then_success_and_input_validation(app_client, provider):
    main, client = app_client
    calls, result = provider
    for body in ({'prompt': ' '}, {'prompt': 'x' * 8001}, {'prompt': 'x', 'kind': 'invalid'},
                 {'prompt': 'x', 'kind': 'template', 'folder_id': 'unexpected'}):
        assert client.post('/api/ai/generate', json=body).status_code == 422
    assert calls == []
    result['exception'] = httpx.ReadTimeout('private timeout details')
    response = client.post('/api/ai/generate', json={'prompt': 'Dokument'})
    assert response.status_code == 504 and 'private timeout details' not in response.text
    assert not main.ai_requests
    result['exception'] = None
    assert client.post('/api/ai/generate', json={'prompt': 'Dokument'}).status_code == 200
    account = client.get('/api/me').json()['id']
    main.ai_requests.add(account)
    try:
        assert client.post('/api/ai/generate', json={'prompt': 'Dokument'}).status_code == 429
    finally:
        main.ai_requests.discard(account)
    assert len(calls) == 2
