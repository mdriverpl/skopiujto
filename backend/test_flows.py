import pytest
from pydantic import ValidationError
from backend.flows import FlowInput
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, create_account, login


def definition(user_id):
    return {'name': 'Obieg faktury', 'description': 'Akceptacja i płatność',
            'trigger': {'event': 'email_received', 'subject_contains': 'faktura', 'attachments_only': True},
            'steps': [{'id': 'accept', 'kind': 'approval', 'title': 'Akceptacja', 'target_type': 'user', 'target_id': user_id},
                      {'id': 'pay', 'kind': 'task', 'title': 'Płatność', 'target_type': 'user', 'target_id': user_id}]}


def test_flow_draft_round_trip_versions_and_delete(app_client):
    main, client = app_client
    me = client.get('/api/me').json()
    body = definition(me['id'])
    created = client.post('/api/flows', json=body)
    assert created.status_code == 201, created.text
    flow = created.json()
    assert flow['status'] == 'draft' and flow['version'] == 1
    assert flow['trigger']['attachments_only'] is True
    assert [step['id'] for step in flow['steps']] == ['accept', 'pay']
    main.initialize()
    assert client.get('/api/flows').json()[0]['id'] == flow['id']
    # A saved definition must never create or execute tasks.
    assert client.get('/api/tasks').json()['sent'] == []
    changed = client.put('/api/flows/' + flow['id'], json={**body, 'name': 'Updated', 'version': 1, 'steps': list(reversed(body['steps']))})
    assert changed.status_code == 200 and changed.json()['version'] == 2
    assert changed.json()['steps'][0]['id'] == 'pay'
    assert client.put('/api/flows/' + flow['id'], json={**body, 'version': 1}).status_code == 409
    assert client.delete('/api/flows/' + flow['id'] + '?version=1').status_code == 409
    assert client.delete('/api/flows/' + flow['id'] + '?version=2').status_code == 204
    assert client.get('/api/flows').json() == []


def test_flow_permissions_and_company_isolation(app_client):
    main, client = app_client
    me = client.get('/api/me').json()
    flow = client.post('/api/flows', json=definition(me['id'])).json()
    reader = create_reader(client)
    login(client, READER)
    assert client.get('/api/flows').json()[0]['id'] == flow['id']
    assert client.post('/api/flows', json=definition(reader['id'])).status_code == 403
    assert client.delete('/api/flows/' + flow['id'] + '?version=1').status_code == 403
    login(client, ADMIN)
    with main.db() as con:
        con.execute('UPDATE users SET is_superadmin=1 WHERE id=?', (me['id'],))
    company = client.post('/api/admin/companies', json={'name': 'Other flow company'}).json()
    other = create_account(client, name='flow-other', password='flow-other-password', role='admin', company_id=company['id'])
    login(client, {'name': 'flow-other', 'password': 'flow-other-password'})
    assert client.get('/api/flows').json() == []
    assert client.put('/api/flows/' + flow['id'], json={**definition(other['id']), 'version': 1}).status_code == 404
    assert client.delete('/api/flows/' + flow['id'] + '?version=1').status_code == 404
    assert client.post('/api/flows', json=definition(me['id'])).status_code == 422
    assert me['id'] not in {person['id'] for person in client.get('/api/flows/options').json()['users']}
    assert client.post('/api/flows', json=definition(other['id'])).status_code == 201
    with main.db() as con:
        con.execute('UPDATE users SET company_id=? WHERE id=?', (me['company_id'], other['id']))
    login(client, ADMIN)
    blocked = client.delete('/api/admin/companies/' + company['id'])
    assert blocked.status_code == 409 and 'Flow' in blocked.json()['detail']
    client.post('/api/logout')
    assert client.get('/api/flows').status_code == 401


def test_flow_group_and_folder_targets_are_validated(app_client):
    _, client = app_client
    me = client.get('/api/me').json()
    group = client.post('/api/admin/groups', json={'name': 'Rozliczenia'}).json()
    folder = client.post('/api/folders', json={'name': 'Faktury', 'access_mode': 'private'}).json()
    options = client.get('/api/flows/options').json()
    assert group['id'] in {row['id'] for row in options['groups']}
    assert folder['id'] in {row['id'] for row in options['folders']}
    body = definition(me['id'])
    body['steps'][0].update(target_type='group', target_id=group['id'])
    body['steps'].insert(0, {'kind': 'save_document', 'title': 'Zapisz fakturę', 'folder_id': folder['id']})
    assert client.post('/api/flows', json=body).status_code == 201
    body['steps'][0]['folder_id'] = 'missing'
    assert client.post('/api/flows', json=body).status_code == 422
    body['steps'].pop(0)
    body['steps'][0]['target_id'] = 'missing'
    assert client.post('/api/flows', json=body).status_code == 422


@pytest.mark.parametrize('change', [
    {'name': '  '}, {'steps': []}, {'trigger': {'event': 'execute_code'}},
    {'steps': [{'kind': 'task', 'title': 'Task'}]},
    {'steps': [{'kind': 'save_document', 'title': 'Save'}]},
    {'steps': [{'kind': 'task', 'title': 'Task', 'target_id': 'me', 'due_days': 0}]},
    {'steps': [{'id': 'same', 'kind': 'task', 'title': 'Task', 'target_id': 'me'}] * 2},
])
def test_flow_definition_validation(change):
    with pytest.raises(ValidationError): FlowInput.model_validate({**definition('me'), **change})
