"""Exercise the real API routes with an isolated, in-memory SQL test adapter."""
import base64
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs
import httpx
import pytest
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.x509.oid import NameOID
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from backend import edelivery, edelivery_connection as integration

ADDRESS = 'AE:PL-12345-67890-ABCDE-12'
CLIENT_FACTORY = httpx.Client

@pytest.fixture
def material():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'test-system')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1))
        .not_valid_after(now+timedelta(days=1)).sign(key, hashes.SHA256()))
    return key, {'private_key': key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode(),
                 'certificate': cert.public_bytes(serialization.Encoding.PEM).decode(), 'key_password': ''}

@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv('EDOCUMENTS_MAIL_SETTINGS_KEY', Fernet.generate_key().decode())
    raw = sqlite3.connect(':memory:', check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.executescript("PRAGMA foreign_keys=ON; CREATE TABLE users(id TEXT PRIMARY KEY); INSERT INTO users VALUES('owner'); INSERT INTO users VALUES('other');")
    raw.executescript(edelivery.SCHEMA + integration.SCHEMA)
    class Connection:
        def execute(self, *args): return raw.execute(*args)
        def begin_write(self): raw.execute('BEGIN IMMEDIATE')
    @contextmanager
    def db():
        try:
            yield Connection()
            raw.commit()
        except Exception:
            raw.rollback()
            raise
    def user(x_user: str | None = Header(default=None)):
        if x_user not in ('owner', 'other'): raise HTTPException(401)
        return {'id': x_user}
    app = FastAPI()
    integration.install(app, db, user, lambda: '2026-10-14T12:00:00Z')
    edelivery.install(app, db, user, lambda: '2026-10-14T12:00:00Z')
    with TestClient(app, headers={'x-user': 'owner'}) as client:
        yield client, raw
    raw.close()

def save(client, data):
    result = client.put('/api/edeliveries/connection', json={'enabled': True, 'address': ADDRESS, 'system_name': 'eDokumenty', **data})
    assert result.status_code == 200, result.text
    return result.json()

def message(identifier='one', remote_status='Doręczona'):
    return {'messageMetadata': {'messageId': identifier, 'subject': 'Pismo', 'timestamp': '2026-10-13T23:30:00Z',
            'from': {'eDeliveryAddress': 'AE:PL-OTHER', 'contributor': {'companyName': 'Office'}}, 'to': [{'eDeliveryAddress': ADDRESS}]},
            'messageControlData': {'messageType': 'Message', 'status': remote_status}}

def mock_operator(monkeypatch, messages, status=200):
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/token'):
            return httpx.Response(200, json={'access_token': 'test-token'})
        assert request.headers['Authorization'] == 'Bearer test-token'
        assert request.method == 'GET'
        assert request.url.params['format'] == 'metadata'
        return httpx.Response(status, json={'messages': messages})
    monkeypatch.setattr(integration.httpx, 'Client', lambda **kwargs: CLIENT_FACTORY(transport=httpx.MockTransport(handler), **kwargs))
    return calls

def test_connection_encrypts_material_preserves_blanks_and_isolates_accounts(api, material):
    client, raw = api
    _, data = material
    saved = save(client, data)
    assert saved['has_private_key'] and saved['has_certificate'] and saved['version'] == 1
    assert 'PRIVATE KEY' not in json.dumps(saved) and 'certificate' not in saved
    row = dict(raw.execute('SELECT * FROM edelivery_connections').fetchone())
    assert data['private_key'] not in row['secrets'] and 'PRIVATE KEY' not in row['config']
    assert integration.stored_secrets(row) == {key: value.strip() for key, value in data.items()}
    result = client.put('/api/edeliveries/connection', json={**saved, 'certificate': '', 'private_key': ''})
    assert result.status_code == 200 and result.json()['version'] == 2
    assert client.put('/api/edeliveries/connection', json=saved).status_code == 409
    client.headers['x-user'] = 'other'
    assert client.get('/api/edeliveries/connection').json()['version'] == 0
    assert client.post('/api/edeliveries/sync').status_code == 422
    assert client.delete('/api/edeliveries/connection').status_code == 204
    assert raw.execute('SELECT count(*) FROM edelivery_connections').fetchone()[0] == 1
    del client.headers['x-user']
    for method, path in [('get', '/api/edeliveries/connection'), ('post', '/api/edeliveries/connection/test'), ('post', '/api/edeliveries/sync'), ('delete', '/api/edeliveries/connection')]:
        assert getattr(client, method)(path).status_code == 401

def test_assertion_is_signed_for_registered_identity_and_production_issuer(material):
    key, data = material
    token = integration.assertion({'address': ADDRESS, 'system_name': 'eDokumenty'}, data)
    header, claims, signature = token.split('.')
    decode = lambda value: base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    key.public_key().verify(decode(signature), (header + '.' + claims).encode(), padding.PKCS1v15(), hashes.SHA256())
    body = json.loads(decode(claims))
    assert body['iss'] == body['sub'] == ADDRESS + '.SYSTEM.eDokumenty'
    assert body['aud'] == integration.ISSUER
    assert body['exp'] - body['iat'] == 60
    assert json.loads(decode(header))['alg'] == 'RS256'
    assert integration.assertion({'address': ADDRESS, 'system_name': 'eDokumenty'}, data) != token

def test_connection_test_checks_token_and_metadata_without_opening_messages(api, material, monkeypatch):
    client, _ = api
    save(client, material[1])
    calls = mock_operator(monkeypatch, [message()])
    response = client.post('/api/edeliveries/connection/test')
    assert response.status_code == 200, response.text
    assert len(calls) == 2 and calls[1].url.params['limit'] == '1'
    form = parse_qs(calls[0].content.decode())
    assert form['grant_type'] == ['client_credentials']
    assert calls[0].url.params['login_hint'] == 'ADE.' + ADDRESS
    assert client.get('/api/edeliveries').json() == []

def test_sync_deduplicates_updates_and_protects_remote_data(api, material, monkeypatch):
    client, _ = api
    save(client, material[1])
    mock_operator(monkeypatch, [message()])
    first = client.post('/api/edeliveries/sync')
    assert first.status_code == 200, first.text
    assert first.json()['added'] == 1
    assert client.post('/api/edeliveries/sync').json()['updated'] == 1
    records = client.get('/api/edeliveries').json()
    assert len(records) == 1 and records[0]['remote_status'] == 'Doręczona'
    assert records[0]['record_date'] == '2026-10-14'  # Warsaw midnight
    item = records[0]
    assert client.patch('/api/edeliveries/' + item['id'], json=item).status_code == 409
    client.headers['x-user'] = 'other'
    assert client.get('/api/edeliveries').json() == []
    client.headers['x-user'] = 'owner'
    assert client.delete('/api/edeliveries/connection').status_code == 204
    assert len(client.get('/api/edeliveries').json()) == 1

def test_failed_or_malformed_sync_keeps_register(api, material, monkeypatch):
    client, _ = api
    save(client, material[1])
    mock_operator(monkeypatch, [message()])
    assert client.post('/api/edeliveries/sync').status_code == 200
    original = client.get('/api/edeliveries').json()
    mock_operator(monkeypatch, [message('new'), {'messageMetadata': {}}])
    assert client.post('/api/edeliveries/sync').status_code == 502
    assert client.get('/api/edeliveries').json() == original
    mock_operator(monkeypatch, [], status=403)
    assert client.post('/api/edeliveries/sync').status_code == 502
    assert client.get('/api/edeliveries').json() == original

def test_invalid_material_and_validation_errors_do_not_echo_private_key(api, material):
    client, _ = api
    _, data = material
    secret = 'private-sensitive-data'
    result = client.put('/api/edeliveries/connection', json={'private_key': secret * 2000})
    assert result.status_code == 422 and secret not in result.text
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    invalid = {**data, 'private_key': other_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()}
    result = client.put('/api/edeliveries/connection', json={'enabled': True, 'address': ADDRESS, 'system_name': 'Test', **invalid})
    assert result.status_code == 422 and 'PRIVATE KEY' not in result.text
    assert client.get('/api/edeliveries/connection').json()['version'] == 0

def test_save_disabled_incomplete_connection_and_block_network(api, monkeypatch):
    client, _ = api
    result = client.put('/api/edeliveries/connection', json={'address': ADDRESS, 'system_name': 'Test'})
    assert result.status_code == 200 and not result.json()['enabled']
    monkeypatch.setattr(integration, 'MailboxClient', lambda *args: pytest.fail('Disabled connection must not use network'))
    assert client.post('/api/edeliveries/connection/test').status_code == 422
    assert client.post('/api/edeliveries/sync').status_code == 422

@pytest.mark.parametrize('curve,algorithm,digest', [
    (ec.SECP256R1(), 'ES256', hashes.SHA256()),
    (ec.SECP384R1(), 'ES384', hashes.SHA384()),
    (ec.SECP521R1(), 'ES512', hashes.SHA512()),
])
def test_ec_assertions_have_raw_jws_signatures(curve, algorithm, digest):
    key = ec.generate_private_key(curve)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ec-system')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1))
        .not_valid_after(now+timedelta(days=1)).sign(key, digest))
    data = {'private_key': key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode(),
            'certificate': cert.public_bytes(serialization.Encoding.PEM).decode()}
    token = integration.assertion({'address': ADDRESS, 'system_name': 'Test'}, data)
    header, claims, signature = token.split('.')
    decode = lambda value: base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    raw = decode(signature)
    size = (key.key_size + 7) // 8
    assert len(raw) == 2 * size
    der = encode_dss_signature(int.from_bytes(raw[:size], 'big'), int.from_bytes(raw[size:], 'big'))
    key.public_key().verify(der, (header + '.' + claims).encode(), ec.ECDSA(digest))
    assert json.loads(decode(header))['alg'] == algorithm

def test_config_change_during_sync_prevents_import(api, material, monkeypatch):
    client, raw = api
    save(client, material[1])
    def handler(request):
        if request.url.path.endswith('/token'): return httpx.Response(200, json={'access_token': 'test-token'})
        raw.execute('UPDATE edelivery_connections SET version=version+1')
        raw.commit()
        return httpx.Response(200, json={'messages': [message()]})
    monkeypatch.setattr(integration.httpx, 'Client', lambda **kwargs: CLIENT_FACTORY(transport=httpx.MockTransport(handler), **kwargs))
    assert client.post('/api/edeliveries/sync').status_code == 409
    assert client.get('/api/edeliveries').json() == []

def test_network_error_is_masked_and_does_not_create_records(api, material, monkeypatch):
    client, _ = api
    save(client, material[1])
    def handler(request): raise httpx.ConnectError('private-provider-error', request=request)
    monkeypatch.setattr(integration.httpx, 'Client', lambda **kwargs: CLIENT_FACTORY(transport=httpx.MockTransport(handler), **kwargs))
    result = client.post('/api/edeliveries/sync')
    assert result.status_code == 502 and 'private-provider-error' not in result.text
    assert client.get('/api/edeliveries').json() == []
