from email.message import EmailMessage
import pytest

from backend.test_storage import app_client
from backend.test_access import READER, create_reader, login
from backend.test_client_mail import imported
from backend.test_mail_sync import imap
from backend.test_mail_settings import account, encryption_key


def assign(client, message, **changes):
    return client.post('/api/client-mail/' + message['id'] + '/company',
                       json={'version': message['version'], 'name': 'Firma Alfa', **changes})


def from_address(client, sender):
    message = EmailMessage()
    message['From'] = sender
    message['Subject'] = 'Test reguł'
    message.set_content('Treść')
    response = client.post('/api/client-mail/import', files={'file': ('mail.eml', message.as_bytes())})
    assert response.status_code == 201, response.text
    return response.json()


def test_company_creates_dictionary_reuses_name_and_exact_address_wins(app_client):
    _, client = app_client
    message = imported(client)
    linked = assign(client, message, scope='domain')
    assert linked.status_code == 200, linked.text
    assert linked.json()['safe'] and linked.json()['company']['name'] == 'Firma Alfa'
    dictionary = client.get('/api/dictionaries').json()[0]
    assert dictionary['name'] == 'Firmy' and dictionary['count'] == 1
    other = from_address(client, 'inny@example.com')
    assert other['safe'] and other['company']['id'] == linked.json()['company']['id']
    assert assign(client, other, name='firma alfa').status_code == 200
    assert client.get('/api/dictionaries').json()[0]['count'] == 1
    specific = assign(client, linked.json(), name='Firma Beta')
    assert specific.status_code == 200, specific.text
    listing = client.get('/api/client-mail').json()
    assert next(m for m in listing if m['id'] == message['id'])['company']['name'] == 'Firma Beta'
    assert next(m for m in listing if m['id'] == other['id'])['company']['name'] == 'Firma Alfa'
    assert not from_address(client, 'jan@sub.example.com')['safe']
    assert not from_address(client, 'jan@otherexample.com')['safe']


def test_existing_dictionary_and_company_edits_are_reflected(app_client):
    _, client = app_client
    dictionary = client.post('/api/dictionaries', json={'name': 'FIRMY', 'fields': ['NIP', 'Nazwa firmy']}).json()
    entry = client.post('/api/dictionaries/' + dictionary['id'] + '/entries', json={'values': {
        'NIP': '123', 'Nazwa firmy': 'Istniejąca'}}).json()
    message = imported(client)
    linked = assign(client, message, entry_id=entry['id'])
    assert linked.status_code == 200 and linked.json()['company']['name'] == 'Istniejąca'
    client.put('/api/dictionaries/' + dictionary['id'] + '/entries/' + entry['id'], json={
        'version': 1, 'values': {'NIP': '123', 'Nazwa firmy': 'Nowa nazwa'}})
    assert client.get('/api/client-mail').json()[0]['company']['name'] == 'Nowa nazwa'
    assert assign(client, linked.json(), name='Dopisano').status_code == 200
    entries = client.get('/api/dictionaries/' + dictionary['id'] + '/entries').json()['entries']
    assert next(e for e in entries if e['values']['Nazwa firmy'] == 'Dopisano')['values']['NIP'] == ''
    client.delete('/api/dictionaries/' + dictionary['id'])
    assert not client.get('/api/client-mail').json()[0]['safe']


def test_block_routes_existing_and_future_mail_and_company_assignment_restores(app_client):
    _, client = app_client
    first = imported(client); second = imported(client)
    unrelated = from_address(client, 'other@example.com')
    url = '/api/client-mail/' + first['id'] + '/spam-address'
    blocked = client.post(url, json={'version': first['version']})
    assert blocked.status_code == 200 and blocked.json()['blocked']
    listing = client.get('/api/client-mail').json()
    assert {m['folder'] for m in listing if m['id'] in (first['id'], second['id'])} == {'spam'}
    assert next(m for m in listing if m['id'] == unrelated['id'])['folder'] == 'inbox'
    future = imported(client)
    assert future['folder'] == 'spam' and not future['safe']
    linked = assign(client, blocked.json())
    assert linked.status_code == 200 and linked.json()['safe'] and linked.json()['folder'] == 'inbox'
    assert all(m['folder'] == 'inbox' for m in client.get('/api/client-mail').json())
    assert imported(client)['safe']


def test_trusted_domain_rejects_spam_address_folder_and_category(app_client):
    _, client = app_client
    linked = assign(client, imported(client), scope='domain').json()
    url = '/api/client-mail/' + linked['id'] + '/spam-address'
    assert client.post(url, json={'version': linked['version']}).status_code == 422
    for changes in ({'folder': 'spam'}, {'category': 'spam'}):
        response = client.patch('/api/client-mail/' + linked['id'], json={'version': linked['version'], **changes})
        assert response.status_code == 422
    row = client.get('/api/client-mail').json()[0]
    assert row['safe'] and not row['blocked'] and row['folder'] == 'inbox'
    assert imported(client)['folder'] == 'inbox'


def test_rules_are_private_and_reject_foreign_entries_and_stale_messages(app_client):
    _, client = app_client
    message = imported(client)
    linked = assign(client, message).json()
    assert assign(client, message).status_code == 409
    assert assign(client, linked, entry_id='missing').status_code == 404
    create_reader(client); login(client, READER)
    assert client.get('/api/client-mail/companies').json() == []
    assert assign(client, linked, entry_id=linked['company']['id']).status_code == 404
    own = imported(client)
    assert not own['safe']
    assert assign(client, own, entry_id=linked['company']['id']).status_code == 404
    assert client.post('/api/client-mail/' + linked['id'] + '/spam-address', json={'version': 1}).status_code == 404
    client.post('/api/logout')
    assert client.get('/api/client-mail/companies').status_code == 401


def test_imap_sync_applies_blocked_address_rules(app_client, imap):
    _, client = app_client
    message = imported(client)
    client.post('/api/client-mail/' + message['id'] + '/spam-address', json={'version': 1})
    assert client.put('/api/client-mail/settings', json=account()).status_code == 200
    response = client.post('/api/client-mail/sync')
    assert response.status_code == 200, response.text
    assert response.json()['imported'] == 2
    assert all(m['folder'] == 'spam' for m in client.get('/api/client-mail').json())


def test_trust_also_restores_legacy_spam_and_ignores_old_address_block(app_client):
    main, client = app_client
    first = assign(client, imported(client)).json()
    with main.db() as con:
        con.execute("UPDATE client_mail SET folder='spam',category='spam',category_source='manual' WHERE id=?", (first['id'],))
        con.execute('INSERT INTO client_mail_spam_addresses(user_id,address) SELECT user_id,sender_email FROM client_mail WHERE id=?', (first['id'],))
    row = next(m for m in client.get('/api/client-mail').json() if m['id'] == first['id'])
    assert row['safe'] and not row['blocked']
    assert client.post('/api/client-mail/spam-scan').status_code == 200
    row = next(m for m in client.get('/api/client-mail').json() if m['id'] == first['id'])
    assert row['folder'] == 'inbox' and not row['category']
    other = from_address(client, 'other@another.example.com')
    assert assign(client, other, name='Inna firma').status_code == 200
    listing = client.get('/api/client-mail').json()
    assert next(m for m in listing if m['id'] == first['id'])['folder'] == 'inbox'


@pytest.mark.parametrize('scope', ['email', 'domain'])
def test_unlink_only_selected_address_preserves_dictionary_and_other_senders(app_client, scope):
    _, client = app_client
    first = assign(client, imported(client), scope=scope).json()
    other = from_address(client, 'other@example.com')
    if scope == 'email': other = assign(client, other).json()
    assert other['safe']
    response = client.request('DELETE', '/api/client-mail/' + first['id'] + '/company', json={
        'version': first['version'], 'entry_id': first['company']['id']})
    assert response.status_code == 200, response.text
    unlinked = response.json()
    assert unlinked['company'] is None and not unlinked['safe'] and unlinked['folder'] == 'inbox'
    listing = client.get('/api/client-mail').json()
    assert next(m for m in listing if m['id'] == other['id'])['safe']
    assert client.get('/api/client-mail/companies').json()[0]['id'] == first['company']['id']
    assert client.get('/api/dictionaries').json()[0]['count'] == 1
    assert not imported(client)['safe']
    # Explicitly assigning this email again clears its domain exclusion.
    reassigned = assign(client, unlinked, entry_id=first['company']['id'])
    assert reassigned.status_code == 200 and reassigned.json()['safe']


def test_unlink_rejects_stale_versions_changed_company_and_other_accounts(app_client):
    _, client = app_client
    original = imported(client)
    linked = assign(client, original).json()
    url = '/api/client-mail/' + linked['id'] + '/company'
    assert client.request('DELETE', url, json={'version': original['version'], 'entry_id': linked['company']['id']}).status_code == 409
    assert client.request('DELETE', url, json={'version': linked['version'], 'entry_id': 'wrong'}).status_code == 409
    assert client.get('/api/client-mail').json()[0]['safe']
    create_reader(client); login(client, READER)
    assert client.request('DELETE', url, json={'version': linked['version'], 'entry_id': linked['company']['id']}).status_code == 404
