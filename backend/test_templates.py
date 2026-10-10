from copy import deepcopy

import pytest
from fastapi import HTTPException

from backend import richtext
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login


FORMATTED = {'type': 'doc', 'content': [
    {'type': 'heading', 'attrs': {'level': 2, 'textAlign': 'center'}, 'content': [
        {'type': 'text', 'text': 'Umowa', 'marks': [{'type': 'bold'}]}]},
    {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Treść umowy', 'marks': [
        {'type': 'italic'}, {'type': 'underline'}, {'type': 'textStyle', 'attrs': {
            'fontFamily': 'Georgia', 'fontSize': '18px', 'color': 'rgb(102, 84, 217)'}}]}]},
    {'type': 'orderedList', 'attrs': {'start': 1, 'type': None}, 'content': [
        {'type': 'listItem', 'content': [{'type': 'paragraph', 'attrs': {'textAlign': None},
          'content': [{'type': 'text', 'text': 'Warunek pierwszy'}]}]}]}
]}


def payload(**extra):
    return {'title': 'Własna umowa', 'category': 'Umowy', 'description': 'Wzór do dostosowania',
            'content': 'Nieaktualny tekst', 'rich_content': deepcopy(FORMATTED), **extra}


def test_template_formatting_round_trip_and_version_conflicts(app_client):
    main, client = app_client
    response = client.post('/api/templates', json=payload())
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['content'] == 'Umowa\nTreść umowy\nWarunek pierwszy'
    assert saved['rich_content'] == richtext.validate(FORMATTED)
    assert saved['version'] == 1 and saved['permissions']['edit']
    listed = next(item for item in client.get('/api/templates').json() if item['id'] == saved['id'])
    assert listed == saved
    update = payload(title='Nowa nazwa', version=1)
    count_before = len(client.get('/api/templates').json())
    updated = client.put(f"/api/templates/{saved['id']}", json=update)
    assert updated.status_code == 200 and updated.json()['version'] == 2
    assert updated.json()['id'] == saved['id']
    assert len(client.get('/api/templates').json()) == count_before
    assert updated.json()['rich_content'] == saved['rich_content']
    assert client.put(f"/api/templates/{saved['id']}", json=update).status_code == 409
    assert client.put(f"/api/templates/{saved['id']}", json=payload()).status_code == 409
    main.initialize()
    assert next(item for item in client.get('/api/templates').json() if item['id'] == saved['id'])['version'] == 2


def test_admin_edits_builtin_in_place_and_migration_preserves_changes(app_client):
    main, client = app_client
    originals = client.get('/api/templates').json()
    assert originals and all(item['user_id'] is None and item['rich_content'] is None for item in originals)
    original = originals[0]
    assert original['permissions']['edit']
    updated = client.put(f"/api/templates/{original['id']}", json=payload(version=1))
    assert updated.status_code == 200
    assert updated.json()['id'] == original['id'] and updated.json()['version'] == 2
    assert updated.json()['user_id'] is None
    assert len(client.get('/api/templates').json()) == len(originals)
    main.initialize()
    reloaded = next(item for item in client.get('/api/templates').json() if item['id'] == original['id'])
    assert reloaded == updated.json()
    copied = client.post('/api/templates', json={**original, 'title': original['title'] + ' — kopia'})
    assert copied.status_code == 201 and copied.json()['user_id'] is not None
    main.initialize()
    assert len([item for item in client.get('/api/templates').json() if item['user_id'] is None]) == len(originals)


def test_non_admin_cannot_change_builtin_even_with_edit_permission(app_client):
    _, client = app_client
    original = client.get('/api/templates').json()[0]
    create_reader(client, can_add=True, can_edit=True)
    login(client, READER)
    builtin = next(item for item in client.get('/api/templates').json() if item['id'] == original['id'])
    assert not builtin['permissions']['edit']
    assert client.put(f"/api/templates/{original['id']}", json=payload(version=1)).status_code == 403
    assert client.post('/api/templates', json=payload()).status_code == 201


def test_only_creator_with_edit_permission_can_edit(app_client):
    main, client = app_client
    own = client.post('/api/templates', json=payload()).json()
    reader = create_reader(client, can_add=True, can_edit=False)
    login(client, READER)
    assert own['id'] not in [item['id'] for item in client.get('/api/templates').json()]
    assert client.put(f"/api/templates/{own['id']}", json=payload(version=1)).status_code == 404
    response = client.post('/api/templates', json=payload())
    assert response.status_code == 201
    reader_template = response.json()
    assert not reader_template['permissions']['edit']
    assert client.put(f"/api/templates/{reader_template['id']}", json=payload(version=1)).status_code == 403
    login(client, ADMIN)
    assert client.put(f"/api/templates/{reader_template['id']}", json=payload(version=1)).status_code == 404
    assert client.patch(f"/api/admin/users/{reader['id']}", json={'can_edit': True}).status_code == 200
    login(client, READER)
    assert client.put(f"/api/templates/{reader_template['id']}", json=payload(version=1)).status_code == 200


def test_readonly_user_cannot_create_template(app_client):
    _, client = app_client
    create_reader(client)
    login(client, READER)
    assert client.post('/api/templates', json=payload()).status_code == 403


def test_document_from_template_preserves_formatting_including_shared_view(app_client):
    _, client = app_client
    saved = client.post('/api/templates', json=payload()).json()
    response = client.post('/api/documents', json={**saved, 'status': 'Szkic'})
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc['rich_content'] == saved['rich_content'] and doc['content'] == saved['content']
    assert client.get(f"/api/documents/{doc['id']}").json()['rich_content'] == saved['rich_content']
    updated = client.put(f"/api/documents/{doc['id']}", json={**doc, 'title': 'Dokument z szablonu'})
    assert updated.status_code == 200
    assert updated.json()['rich_content'] == saved['rich_content']
    share = client.post(f"/api/documents/{doc['id']}/shares", json={'hours': 1}).json()
    client.post('/api/logout')
    shared = client.get('/api/shared/' + share['path'].split('/')[-1])
    assert shared.status_code == 200 and shared.json()['rich_content'] == saved['rich_content']


@pytest.mark.parametrize('invalid', [
    {'type': []}, {'type': 'doc', 'content': [None]},
    {'type': 'doc', 'content': [{'type': 'script', 'text': 'alert(1)'}]},
    {'type': 'doc', 'content': [{'type': 'paragraph', 'attrs': {'onclick': 'alert(1)'}}]},
    {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'x', 'marks': [
        {'type': 'link', 'attrs': {'href': 'javascript:alert(1)'}}]}]}]},
    {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'x', 'marks': [
        {'type': 'textStyle', 'attrs': {'fontFamily': 'url(https://example.invalid)'}}]}]}]},
])
def test_unsupported_formatting_rejected_without_database_changes(app_client, invalid):
    _, client = app_client
    before = client.get('/api/templates').json()
    assert client.post('/api/templates', json=payload(rich_content=invalid)).status_code == 422
    assert client.post('/api/documents', json=payload(rich_content=invalid)).status_code == 422
    assert client.get('/api/templates').json() == before
    assert client.get('/api/documents').json() == []


def test_legacy_plain_text_and_limits(app_client):
    _, client = app_client
    raw = '<script>alert(1)</script>\nZwykły tekst'
    saved = client.post('/api/templates', json=payload(content=raw, rich_content=None)).json()
    assert saved['content'] == raw and saved['rich_content'] is None
    deep = {'type': 'paragraph'}
    for _ in range(35):
        deep = {'type': 'blockquote', 'content': [deep]}
    with pytest.raises(HTTPException) as caught:
        richtext.validate({'type': 'doc', 'content': [deep]})
    assert caught.value.status_code == 413
    large = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'x' * 500001}]}]}
    assert client.post('/api/templates', json=payload(rich_content=large)).status_code == 413


def test_delete_own_template_keeps_created_documents(app_client):
    main, client = app_client
    saved = client.post('/api/templates', json=payload()).json()
    doc = client.post('/api/documents', json={**saved, 'status': 'Szkic'}).json()
    assert saved['permissions']['delete']
    response = client.delete(f"/api/templates/{saved['id']}")
    assert response.status_code == 204 and not response.content
    assert saved['id'] not in [item['id'] for item in client.get('/api/templates').json()]
    assert client.get(f"/api/documents/{doc['id']}").json()['rich_content'] == saved['rich_content']
    assert client.delete(f"/api/templates/{saved['id']}").status_code == 404
    main.initialize()
    assert saved['id'] not in [item['id'] for item in client.get('/api/templates').json()]


def test_admin_deletes_builtin_without_recreating_it_after_restart(app_client):
    main, client = app_client
    before = client.get('/api/templates').json()
    original = before[0]
    assert original['user_id'] is None and original['permissions']['delete']
    assert client.delete(f"/api/templates/{original['id']}").status_code == 204
    main.initialize()
    main.initialize()
    after = client.get('/api/templates').json()
    assert len(after) == len(before) - 1
    assert original['id'] not in [item['id'] for item in after]


def test_delete_requires_owner_and_delete_permission(app_client):
    _, client = app_client
    admin_template = client.post('/api/templates', json=payload()).json()
    builtin = next(item for item in client.get('/api/templates').json() if item['user_id'] is None)
    reader = create_reader(client, can_add=True, can_edit=True, can_delete=False)
    login(client, READER)
    own = client.post('/api/templates', json=payload()).json()
    assert own['permissions']['edit'] and not own['permissions']['delete']
    assert client.delete(f"/api/templates/{own['id']}").status_code == 403
    assert client.delete(f"/api/templates/{admin_template['id']}").status_code == 404
    assert client.delete(f"/api/templates/{builtin['id']}").status_code == 403
    login(client, ADMIN)
    assert client.delete(f"/api/templates/{own['id']}").status_code == 404
    assert client.patch(f"/api/admin/users/{reader['id']}", json={'can_delete': True, 'can_edit': False}).status_code == 200
    login(client, READER)
    loaded = next(item for item in client.get('/api/templates').json() if item['id'] == own['id'])
    assert loaded['permissions']['delete'] and not loaded['permissions']['edit']
    assert client.delete(f"/api/templates/{builtin['id']}").status_code == 403
    assert client.delete(f"/api/templates/{own['id']}").status_code == 204
    client.post('/api/logout')
    assert client.delete(f"/api/templates/{builtin['id']}").status_code == 401

