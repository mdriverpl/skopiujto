import pytest
from pydantic import ValidationError
from backend.edelivery import DeliveryInput
from backend.test_storage import app_client
from backend.test_access import READER, create_reader, login

def delivery(**changes):
    return {'title': '  Pismo  ', 'correspondent': '  Urząd  ', 'reference': 'REF-1',
            'direction': 'incoming', 'status': 'registered', 'record_date': '2026-10-14', **changes}

def test_register_persists_updates_dates_and_rejects_conflicts(app_client):
    _, client = app_client
    response = client.post('/api/edeliveries', json=delivery())
    assert response.status_code == 201, response.text
    item = response.json()
    assert item['title'] == 'Pismo' and item['correspondent'] == 'Urząd'
    url = '/api/edeliveries/' + item['id']
    changed = client.patch(url, json=delivery(status='received', notes='Potwierdzenie', version=1))
    assert changed.status_code == 200 and changed.json()['version'] == 2
    assert client.patch(url, json=delivery(version=1)).status_code == 409
    assert client.patch(url, json=delivery()).status_code == 409
    assert client.get('/api/edeliveries').json() == [changed.json()]
    client.post('/api/edeliveries', json=delivery(record_date='2026-10-15'))
    assert client.get('/api/edeliveries').json()[0]['record_date'] == '2026-10-15'
    assert client.delete(url).status_code == 204
    assert all(record['id'] != item['id'] for record in client.get('/api/edeliveries').json())

def test_register_is_private_and_requires_authentication(app_client):
    _, client = app_client
    item = client.post('/api/edeliveries', json=delivery()).json()
    create_reader(client); login(client, READER)
    url = '/api/edeliveries/' + item['id']
    assert client.get('/api/edeliveries').json() == []
    assert client.patch(url, json=delivery(version=1)).status_code == 404
    assert client.delete(url).status_code == 404
    assert client.post('/api/edeliveries', json=delivery()).status_code == 201
    client.post('/api/logout')
    assert client.get('/api/edeliveries').status_code == 401
    assert client.post('/api/edeliveries', json=delivery()).status_code == 401
    assert client.patch(url, json=delivery(version=1)).status_code == 401
    assert client.delete(url).status_code == 401

@pytest.mark.parametrize('changes', [
    {'title': '  '}, {'correspondent': '  '}, {'title': 'x' * 201},
    {'status': 'unknown'}, {'direction': 'unknown'}, {'record_date': '2026-02-30'},
    {'record_date': ''}, {'notes': 'x' * 20001}, {'version': 0},
])
def test_delivery_input_rejects_invalid_records(changes):
    with pytest.raises(ValidationError):
        DeliveryInput(**delivery(**changes))

def test_delivery_input_normalizes_text_and_keeps_calendar_date():
    item = DeliveryInput(**delivery(address=' AE:123 ', reference=' REF-1 '))
    assert item.title == 'Pismo' and item.correspondent == 'Urząd'
    assert item.address == 'AE:123' and item.reference == 'REF-1'
    assert item.record_date.isoformat() == '2026-10-14'
