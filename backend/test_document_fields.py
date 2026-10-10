from copy import deepcopy

import pytest

from backend import document_fields, richtext
from backend.test_storage import app_client
from backend.test_access import READER, create_reader, login

SOURCE = {'type': 'doc', 'content': [
    {'type': 'heading', 'attrs': {'level': 2}, 'content': [{'type': 'text', 'text': 'Umowa sprzedaży'}]},
    {'type': 'paragraph', 'content': [
        {'type': 'text', 'text': 'Sprzedający: [imię sprzedającego]. Kupujący: [imię kupującego].'}]},
    {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Cena: '},
        {'type': 'text', 'text': '[ce', 'marks': [{'type': 'bold'}]}, {'type': 'text', 'text': 'na] zł.'}]},
    {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Podpis: [ Imię sprzedającego ]'}]}
]}


def test_fields_persist_and_can_be_changed_after_reopening(app_client):
    main, client = app_client
    body = {'title': 'Umowa sprzedaży', 'field_source': deepcopy(SOURCE),
            'field_values': {'imię sprzedającego': 'Anna', 'imię kupującego': 'Jan', 'cena': '1200'},
            'content': 'Ignored content', 'rich_content': None}
    response = client.post('/api/documents', json=body)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['field_source'] == SOURCE and saved['field_values'] == body['field_values']
    assert saved['content'] == 'Umowa sprzedaży\nSprzedający: Anna. Kupujący: Jan.\nCena: 1200 zł.\nPodpis: Anna'
    price = next(node for node in saved['rich_content']['content'][2]['content'] if node.get('text') == '1200')
    assert price['marks'] == [{'type': 'bold'}]
    main.initialize()
    loaded = client.get(f"/api/documents/{saved['id']}").json()
    assert loaded['field_source'] == SOURCE and loaded['field_values'] == body['field_values']
    update = {**loaded, 'field_values': {**loaded['field_values'], 'cena': '2000'}}
    updated = client.put(f"/api/documents/{saved['id']}", json=update)
    assert updated.status_code == 200 and 'Cena: 2000 zł.' in updated.json()['content']
    cleared = {**updated.json(), 'field_values': {}}
    empty = client.put(f"/api/documents/{saved['id']}", json=cleared)
    assert empty.status_code == 200 and empty.json()['content'] == richtext.plain_text(SOURCE)


def test_shared_document_shows_filled_contract_without_source_metadata(app_client):
    _, client = app_client
    saved = client.post('/api/documents', json={'title': 'Umowa', 'field_source': SOURCE,
        'field_values': {'imię sprzedającego': 'Anna', 'cena': '1000'}}).json()
    share = client.post(f"/api/documents/{saved['id']}/shares", json={'hours': 1}).json()
    client.post('/api/logout')
    shared = client.get('/api/shared/' + share['path'].split('/')[-1]).json()
    assert 'Cena: 1000 zł.' in shared['content']
    assert 'field_values' not in shared and 'field_source' not in shared
    assert shared['rich_content'] == saved['rich_content']


@pytest.mark.parametrize('extra', [
    {'field_source': SOURCE, 'field_values': {'unexpected': 'x'}},
    {'field_source': SOURCE, 'field_values': {'cena': 'x' * 2001}},
    {'field_source': None, 'field_values': {'cena': '1000'}},
    {'field_source': {'type': 'doc', 'content': [{'type': 'script', 'text': 'bad'}]}}
])
def test_invalid_fields_are_rejected_without_saving(app_client, extra):
    _, client = app_client
    assert client.post('/api/documents', json={'title': 'Umowa', **extra}).status_code == 422
    assert client.get('/api/documents').json() == []


def test_literal_values_and_existing_author_permissions(app_client):
    _, client = app_client
    saved = client.post('/api/documents', json={'title': 'Umowa', 'field_source': SOURCE,
        'field_values': {'imię sprzedającego': '<script>[cena]</script>', 'cena': '1000'}}).json()
    assert '<script>[cena]</script>' in saved['content'] and 'Cena: 1000 zł.' in saved['content']
    create_reader(client, can_edit=True)
    login(client, READER)
    assert client.put(f"/api/documents/{saved['id']}", json={**saved, 'field_values': {'cena': '999'}}).status_code in (403, 404)


def test_many_fields_exceed_limit(app_client):
    _, client = app_client
    source = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [
        {'type': 'text', 'text': ' '.join(f'[pole {i}]' for i in range(201))}]}]}
    assert client.post('/api/documents', json={'title': 'Umowa', 'field_source': source}).status_code == 413
