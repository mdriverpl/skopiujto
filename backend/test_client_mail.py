from email.message import EmailMessage
import pytest
from fastapi import HTTPException
from backend import client_mail, mailer, ai
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login


def eml():
    message = EmailMessage()
    message['From'] = 'Jan Kowalski <jan@example.com>'
    message['To'] = 'me@example.com'
    message['Subject'] = 'Oferta współpracy'
    message.set_content('Dzień dobry, proszę o odpowiedź na ofertę.')
    message.add_attachment(b'PDF bytes', maintype='application', subtype='pdf', filename='Oferta.pdf')
    return message.as_bytes()


def imported(client):
    result = client.post('/api/client-mail/import', files={'file': ('mail.eml', eml(), 'message/rfc822')})
    assert result.status_code == 201, result.text
    return result.json()


def test_import_read_tag_archive_attachment_and_conflict(app_client):
    _, client = app_client
    message = imported(client)
    assert message['unread'] == 1 and message['subject'] == 'Oferta współpracy'
    assert message['attachments'][0]['name'] == 'Oferta.pdf'
    url = '/api/client-mail/' + message['id']
    part = client.get(url + '/attachments/' + message['attachments'][0]['id'])
    assert part.content == b'PDF bytes' and 'attachment' in part.headers['content-disposition']
    updated = client.patch(url, json={'version': 1, 'unread': False, 'label': 'urgent', 'starred': True}).json()
    assert updated['version'] == 2 and updated['unread'] == 0 and updated['starred'] == 1
    assert client.patch(url, json={'version': 1, 'folder': 'trash'}).status_code == 409
    assert client.patch(url, json={'version': 2, 'folder': 'archive'}).json()['folder'] == 'archive'
    assert client.get('/api/client-mail').json()[0]['folder'] == 'archive'


def test_mail_and_attachments_are_private_and_require_authentication(app_client):
    _, client = app_client
    message = imported(client)
    url = '/api/client-mail/' + message['id']
    create_reader(client); login(client, READER)
    assert client.get('/api/client-mail').json() == []
    assert client.patch(url, json={'version': 1, 'folder': 'trash'}).status_code == 404
    assert client.get(url + '/attachments/' + message['attachments'][0]['id']).status_code == 404
    assert client.post(url + '/analysis').status_code == 404
    client.post('/api/logout')
    assert client.get('/api/client-mail').status_code == 401
    assert client.post('/api/client-mail/drafts', json={}).status_code == 401


def test_send_failure_retains_draft_success_is_not_sent_twice(app_client, monkeypatch):
    _, client = app_client
    draft = client.post('/api/client-mail/drafts', json={
        'recipient': 'anna@example.com', 'subject': 'Oferta', 'content': 'Dzień dobry'}).json()
    url = '/api/client-mail/' + draft['id']
    monkeypatch.setattr(mailer, 'configuration', lambda: {'sender': 'sender@example.com'})
    def fail(*args): raise HTTPException(503, 'SMTP unavailable')
    monkeypatch.setattr(mailer, 'send_message', fail)
    assert client.post(url + '/send', json={'version': 1}).status_code == 503
    assert client.get('/api/client-mail').json()[0]['folder'] == 'drafts'
    sent = []
    monkeypatch.setattr(mailer, 'send_message', lambda *args: sent.append(args))
    result = client.post(url + '/send', json={'version': 1})
    assert result.status_code == 200 and result.json()['folder'] == 'sent'
    assert len(sent) == 1 and sent[0][1] == 'anna@example.com'
    assert client.post(url + '/send', json={'version': 2}).status_code == 409
    assert len(sent) == 1


def test_draft_validation_and_edit_conflict(app_client):
    _, client = app_client
    for body in ({'subject': 'Header\r\nBcc: hacker@example.com'}, {'content': 'x' * 100001}):
        assert client.post('/api/client-mail/drafts', json=body).status_code == 422
    draft = client.post('/api/client-mail/drafts', json={}).json()
    url = '/api/client-mail/' + draft['id']
    assert client.put(url + '/draft', json={'version': 1, 'subject': 'Nowy'}).json()['version'] == 2
    assert client.put(url + '/draft', json={'version': 1, 'subject': 'Stary'}).status_code == 409
    assert client.post(url + '/send', json={'version': 2}).status_code == 422
    assert client.post('/api/client-mail/import', files={'file': ('bad.txt', b'bad')}).status_code == 422
    assert client.post('/api/client-mail/import', files={'file': ('bad.eml', b'not an email')}).status_code == 422
    assert client.put('/api/me/menu-order', json={'menu_order': ['mail', 'start']}).status_code == 200


def test_analysis_uses_mail_as_data_and_does_not_send(app_client, monkeypatch):
    _, client = app_client
    message = imported(client)
    calls = []
    async def response(instructions, data, schema, name, convert):
        calls.append((instructions, data))
        return convert({'summary': 'Prośba o odpowiedź.', 'priority': 'high',
                        'tasks': ['Odpowiedzieć na ofertę'], 'reply': 'Dziękuję za ofertę.'})
    monkeypatch.setattr(ai, 'structured_response', response)
    result = client.post('/api/client-mail/' + message['id'] + '/analysis')
    assert result.status_code == 200 and result.json()['reply'] == 'Dziękuję za ofertę.'
    assert 'niezaufane dane' in calls[0][0]
    assert 'proszę o odpowiedź' in calls[0][1]
    assert len(client.get('/api/client-mail').json()) == 1


def test_html_import_removes_active_content_and_external_images():
    message = EmailMessage()
    message['From'] = 'test@example.com'
    message.set_content('<p>Ważna oferta</p><script>alert(1)</script><img src="https://tracker.invalid">', subtype='html')
    parsed = client_mail.parse_message(message.as_bytes())
    assert 'Ważna oferta' in parsed['content']
    assert 'alert' not in parsed['content'] and 'tracker' not in parsed['content']
