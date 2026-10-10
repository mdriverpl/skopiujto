import json

import httpx
import pytest

from backend import ai_memory
from backend.test_storage import app_client
from backend.test_ai import provider, output
from backend.test_access import ADMIN, READER, create_reader, login

MEMORY = {'name': 'Moja firma', 'fields': {'nazwa sprzedającego': 'Firma Alfa',
          'adres sprzedającego': 'Długa 1', 'miejsce zawarcia umowy': 'Warszawa'}}
REQUEST = {'title': 'Umowa', 'context': 'Sprzedający: Firma Alfa. Zawarto w [miejsce podpisania].',
           'fields': ['miejsce podpisania', 'adres sprzedającego'], 'values': {'nazwa sprzedającego': 'Firma Alfa'}}


def test_live_memory_updates_one_record_persists_and_keeps_accounts_separate(app_client):
    main, client = app_client
    body = {**MEMORY, 'source_key': 'document-one', 'context': REQUEST['context']}
    first = client.post('/api/saved-data/remember', json=body)
    assert first.status_code == 200, first.text
    updated = client.post('/api/saved-data/remember', json={**body, 'fields': {
        **body['fields'], 'adres sprzedającego': 'Długa 2'}}).json()
    assert updated['id'] == first.json()['id'] and updated['version'] == 2
    assert len(client.get('/api/saved-data').json()) == 1
    main.initialize()
    assert client.get('/api/saved-data').json()[0]['fields']['adres sprzedającego'] == 'Długa 2'
    create_reader(client); login(client, READER)
    other = client.post('/api/saved-data/remember', json=body).json()
    assert other['id'] != updated['id']
    assert len(client.get('/api/saved-data').json()) == 1
    login(client, ADMIN)
    assert client.get('/api/saved-data').json() == [updated]
    assert client.delete('/api/saved-data/' + updated['id']).status_code == 204
    # Deleting a memory also removes its source mapping, so subsequent edits can recreate it.
    recreated = client.post('/api/saved-data/remember', json=body)
    assert recreated.status_code == 200 and recreated.json()['id'] != updated['id']
    client.post('/api/logout')
    assert client.post('/api/saved-data/remember', json=body).status_code == 401


def test_semantic_match_uses_only_saved_values_and_private_context(app_client, provider):
    _, client = app_client
    calls, result = provider
    create_reader(client); login(client, READER)
    client.post('/api/saved-data/remember', json={'name': 'Foreign private', 'fields': {'secret': 'Foreign address'},
        'source_key': 'foreign', 'context': 'Foreign contract'})
    login(client, ADMIN)
    saved = client.post('/api/saved-data/remember', json={**MEMORY, 'source_key': 'one', 'context': 'Historical contract'}).json()
    result['json'] = output({'matches': [{'field': 'miejsce podpisania', 'candidate_id': saved['id'] + ':2', 'confidence': .99}]})
    response = client.post('/api/saved-data/match', json=REQUEST)
    assert response.status_code == 200, response.text
    assert response.json()['matches']['miejsce podpisania'] == {'value': 'Warszawa', 'source': MEMORY['name']}
    payload = json.loads(calls[0].content)
    assert payload['store'] is False and payload['text']['format']['strict'] is True
    material = json.loads(payload['input'])
    assert material['document']['values']['nazwa sprzedającego'] == 'Firma Alfa'
    assert material['memories'][0]['context'] == 'Historical contract'
    assert 'Foreign private' not in payload['input'] and 'Foreign address' not in payload['input']
    assert len(client.get('/api/saved-data').json()) == 1
    assert client.get('/api/documents').json() == []


@pytest.mark.parametrize('case', ['invented_reference', 'unknown_field', 'low_confidence', 'duplicate', 'already_filled', 'wrong_party'])
def test_uncertain_or_invalid_references_never_fill_fields(app_client, provider, case):
    _, client = app_client
    _, result = provider
    saved = client.post('/api/saved-data', json=MEMORY).json()
    selection = {'field': 'miejsce podpisania', 'candidate_id': saved['id'] + ':2', 'confidence': .99}
    request = {**REQUEST, 'values': {**REQUEST['values']}}
    matches = [selection]
    if case == 'invented_reference': selection['candidate_id'] = 'invented'
    if case == 'unknown_field': selection['field'] = 'nieistniejące pole'
    if case == 'low_confidence': selection['confidence'] = .8
    if case == 'duplicate': matches.append(dict(selection))
    if case == 'already_filled': request['values']['miejsce podpisania'] = 'Poznań'
    if case == 'wrong_party':
        request['fields'] = ['adres kupującego']
        selection.update(field='adres kupującego', candidate_id=saved['id'] + ':1')
    result['json'] = output({'matches': matches})
    response = client.post('/api/saved-data/match', json=request)
    assert response.status_code == 200 and response.json()['matches'] == {}


def test_no_memory_or_no_empty_fields_skips_provider_and_anonymous_requests_rejected(app_client, provider):
    _, client = app_client
    calls, _ = provider
    assert client.post('/api/saved-data/match', json=REQUEST).json() == {'matches': {}}
    client.post('/api/saved-data', json=MEMORY)
    assert client.post('/api/saved-data/match', json={**REQUEST, 'fields': []}).json() == {'matches': {}}
    assert calls == []
    client.post('/api/logout')
    assert client.post('/api/saved-data/match', json=REQUEST).status_code == 401


@pytest.mark.parametrize('bad', [
    {'status': 'incomplete', 'output': []}, output({'matches': [{'field': 'x', 'candidate_id': 'x', 'confidence': 2}]}),
    output({'matches': [{'field': 'x', 'value': 'Invented address'}]}),
])
def test_invalid_provider_results_leave_memory_unchanged(app_client, provider, bad):
    _, client = app_client
    _, result = provider
    saved = client.post('/api/saved-data', json=MEMORY).json()
    result['json'] = bad
    assert client.post('/api/saved-data/match', json=REQUEST).status_code == 502
    assert client.get('/api/saved-data').json() == [saved]


def test_ai_failure_and_missing_key_do_not_prevent_remembering(app_client, provider, monkeypatch):
    _, client = app_client
    calls, result = provider
    client.post('/api/saved-data', json=MEMORY)
    result['exception'] = httpx.ReadTimeout('Do not expose')
    assert client.post('/api/saved-data/match', json=REQUEST).status_code == 504
    monkeypatch.delenv('OPENAI_API_KEY')
    assert client.post('/api/saved-data/match', json=REQUEST).status_code == 503
    assert len(calls) == 1
    assert client.post('/api/saved-data/remember', json={**MEMORY, 'source_key': 'one'}).status_code == 200


@pytest.mark.parametrize('extra', [
    {'fields': ['[bad]']}, {'fields': ['x' * 121]}, {'values': {'x': 'a' * 2001}},
    {'fields': ['x'] * 201}, {'context': 'x' * 40001},
])
def test_invalid_matching_request_does_not_call_provider(app_client, provider, extra):
    _, client = app_client
    calls, _ = provider
    client.post('/api/saved-data', json=MEMORY)
    assert client.post('/api/saved-data/match', json={**REQUEST, **extra}).status_code == 422
    assert calls == []
