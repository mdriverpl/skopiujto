import pytest

from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login
from backend.test_mailing import smtp, send, token

def uploaded(client, filename='contract.pdf', **fields):
    response = client.post('/api/files', data=fields, files={'file': (filename, b'original-file')})
    assert response.status_code == 201, response.text
    return response.json()

def status(client, doc, value):
    return client.patch(f"/api/documents/{doc['id']}/status", json={'status': value, 'version': doc['version']})

def listed(client, doc):
    return next(item for item in client.get('/api/documents').json() if item['id'] == doc['id'])

@pytest.mark.parametrize('value,kind', [('Do podpisania', 'signature'), ('Do modyfikacji', 'modification'), ('Do akceptacji', 'approval'), ('W toku', 'in_progress'), ('Szkic', 'modification'), ('Gotowy', None), ('Archiwum', None)])
def test_status_drives_activity_and_finishing(app_client, value, kind):
    _, client = app_client
    doc = uploaded(client)
    response = status(client, doc, value)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['status'] == value
    actions = listed(client, doc)['active_actions']
    assert [action['kind'] for action in actions] == ([kind] if kind else [])
    assert status(client, saved, value).json()['version'] == saved['version']
    if value != 'Gotowy':
        assert status(client, doc, 'Gotowy').status_code == 409

def test_scratch_document_and_open_deadlines(app_client):
    _, client = app_client
    doc = client.post('/api/documents', json={'title': 'Text'}).json()
    assert listed(client, doc)['active_actions'][0]['kind'] == 'modification'
    doc = status(client, doc, 'Gotowy').json()
    with_deadline = client.post(f"/api/documents/{doc['id']}/deadlines", json={'title': 'Review', 'due_at': '2026-10-20T12:00:00Z'}).json()
    assert listed(client, doc)['active_actions'] == [{'kind': 'deadline', 'label': 'Otwarty termin', 'count': 1}]
    deadline = with_deadline['deadlines'][0]
    assert client.patch(f"/api/documents/{doc['id']}/deadlines/{deadline['id']}", json={'done': True}).status_code == 200
    assert not listed(client, doc)['active_actions']

def test_image_status_does_not_replace_or_enable_generic_edits(app_client):
    _, client = app_client
    doc = uploaded(client, 'image.png')
    assert doc['permissions']['workflow'] and not doc['permissions']['edit']
    saved = status(client, doc, 'Do modyfikacji').json()
    assert saved['status'] == 'Do modyfikacji' and not saved['permissions']['edit']
    assert client.get(f"/api/documents/{doc['id']}/file").content == b'original-file'
    assert client.put(f"/api/documents/{doc['id']}", json={'title': 'Changed', 'version': saved['version']}).status_code == 403

def test_hidden_and_shared_files_never_gain_status_permissions(app_client):
    _, client = app_client
    reader = create_reader(client, role='admin', can_edit=True, can_add=True)
    private = client.post('/api/folders', json={'name': 'Private', 'access_mode': 'private'}).json()
    hidden = uploaded(client, folder_id=private['id'])
    shared = client.post('/api/folders', json={'name': 'Shared', 'access_mode': 'users', 'user_ids': [reader['id']], 'can_edit': True}).json()
    doc = uploaded(client, folder_id=shared['id'])
    doc = status(client, doc, 'Do podpisania').json()
    login(client, READER)
    rows = client.get('/api/documents').json()
    assert hidden['id'] not in [item['id'] for item in rows]
    assert rows[0]['active_actions'][0]['kind'] == 'signature'
    assert not rows[0]['permissions']['workflow']
    assert status(client, doc, 'Gotowy').status_code == 403
    assert status(client, hidden, 'Gotowy').status_code == 404
    own = uploaded(client)
    login(client, ADMIN)
    assert client.patch(f"/api/admin/users/{reader['id']}", json={'can_edit': False}).status_code == 200
    login(client, READER)
    assert status(client, own, 'Do podpisania').status_code == 403

def test_pending_approvals_across_versions_and_completion(app_client, smtp):
    _, client = app_client
    doc = uploaded(client)
    assert send(client, doc).status_code == 201
    assert listed(client, doc)['active_actions'] == [{'kind': 'approval', 'label': 'Oczekuje na akceptację', 'count': 1}]
    doc = status(client, doc, 'W toku').json()
    assert listed(client, doc)['approvals']['waiting'] == 0
    assert [action['kind'] for action in listed(client, doc)['active_actions']] == ['in_progress', 'approval']
    assert client.post('/api/approvals/' + token(smtp) + '/accept', json={'confirmed': True}).status_code == 200
    assert [action['kind'] for action in listed(client, doc)['active_actions']] == ['in_progress']
    doc = status(client, doc, 'Gotowy').json()
    assert not listed(client, doc)['active_actions']

def test_archived_and_expired_approval_requests_are_inactive(app_client, smtp):
    main, client = app_client
    doc = uploaded(client)
    assert send(client, doc).status_code == 201
    archived = status(client, doc, 'Archiwum').json()
    assert not listed(client, doc)['active_actions']
    doc = status(client, archived, 'Gotowy').json()
    assert listed(client, doc)['active_actions']
    with main.db() as c:
        c.execute('UPDATE file_mailings SET expires=0')
    assert not listed(client, doc)['active_actions']

def test_invalid_status_and_unauthenticated_changes(app_client):
    _, client = app_client
    doc = uploaded(client)
    assert status(client, doc, 'Unknown').status_code == 422
    assert listed(client, doc)['status'] == 'Gotowy'
    client.post('/api/logout')
    assert status(client, doc, 'Do podpisania').status_code == 401
