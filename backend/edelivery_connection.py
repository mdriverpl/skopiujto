"""Personal Poczta Polska UA API v3 connections; metadata-only synchronization."""
import base64
import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.fernet import InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi import Depends, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from backend.mail_settings import cipher

ISSUER = 'https://ow.edoreczenia.gov.pl/auth/realms/EDOR'
TOKEN_URL = ISSUER + '/protocol/openid-connect/token'
API_URL = 'https://uaapi-ow.poczta-polska.pl/api/v3'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS edelivery_connections(
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 config TEXT NOT NULL, secrets TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS edelivery_imports(
 record_id TEXT PRIMARY KEY REFERENCES edelivery_records(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 mailbox_address TEXT NOT NULL, message_id TEXT NOT NULL, remote_status TEXT NOT NULL,
 synced_at TEXT NOT NULL, UNIQUE(user_id,mailbox_address,message_id));
'''


class ConnectionInput(BaseModel):
    enabled: bool = False
    address: str = Field(default='', max_length=100)
    system_name: str = Field(default='', max_length=100)
    certificate: str | None = Field(default=None, max_length=32000)
    private_key: str | None = Field(default=None, max_length=32000)
    key_password: str | None = Field(default=None, max_length=1000)
    version: int = Field(default=0, ge=0)

    @field_validator('address', 'system_name')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if any(ord(char) < 32 for char in value):
            raise ValueError('Usuń znaki sterujące z danych systemu.')
        return value

    @field_validator('address')
    @classmethod
    def valid_address(cls, value):
        if value and (not value.startswith('AE:') or any(char not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:-' for char in value)):
            raise ValueError('Podaj adres ADE w formacie AE:PL-… .')
        return value


def private_material(data):
    try:
        password = data.get('key_password') or ''
        key = serialization.load_pem_private_key(data['private_key'].encode(), password.encode() if password else None)
        cert = x509.load_pem_x509_certificate(data['certificate'].encode())
        if not isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)):
            raise ValueError()
        if isinstance(key, rsa.RSAPrivateKey) and key.key_size < 2048:
            raise ValueError()
        if isinstance(key, ec.EllipticCurvePrivateKey) and key.curve.name not in ('secp256r1', 'secp384r1', 'secp521r1'):
            raise ValueError()
        encoding = serialization.Encoding.DER
        form = serialization.PublicFormat.SubjectPublicKeyInfo
        if key.public_key().public_bytes(encoding, form) != cert.public_key().public_bytes(encoding, form):
            raise ValueError()
        now = datetime.now(timezone.utc)
        if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
            raise ValueError()
        return key, cert
    except (ValueError, TypeError, KeyError, UnsupportedAlgorithm):
        raise HTTPException(422, 'Sprawdź certyfikat PEM, klucz prywatny PEM, jego hasło i datę ważności. Certyfikat musi odpowiadać kluczowi.') from None


def stored_secrets(row):
    try:
        return json.loads(cipher().decrypt(row['secrets'].encode()))
    except (InvalidToken, ValueError):
        raise HTTPException(503, 'Nie można odszyfrować danych eDoręczeń. Przywróć właściwy EDOCUMENTS_MAIL_SETTINGS_KEY na serwerze.') from None


def public_settings(row):
    if not row:
        return {'enabled': False, 'address': '', 'system_name': '', 'has_certificate': False, 'has_private_key': False, 'version': 0}
    return {**json.loads(row['config']), 'version': row['version']}


def load_connection(con, current):
    row = con.execute('SELECT * FROM edelivery_connections WHERE user_id=?', (current['id'],)).fetchone()
    if not row:
        raise HTTPException(422, 'Najpierw zapisz konfigurację skrzynki eDoręczeń.')
    config = {**json.loads(row['config']), 'version': row['version']}
    if not config['enabled']:
        raise HTTPException(422, 'Włącz połączenie ze skrzynką eDoręczeń w ustawieniach.')
    return config, stored_secrets(row)


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def assertion(config, data):
    key, _ = private_material(data)
    if isinstance(key, rsa.RSAPrivateKey):
        algorithm, digest = 'RS256', hashes.SHA256()
    else:
        algorithm, digest = {256: ('ES256', hashes.SHA256()), 384: ('ES384', hashes.SHA384()), 521: ('ES512', hashes.SHA512())}[key.key_size]
    client_id = f"{config['address']}.SYSTEM.{config['system_name']}"
    timestamp = int(time.time())
    claims = {'iss': client_id, 'sub': client_id, 'aud': ISSUER, 'iat': timestamp, 'nbf': timestamp, 'exp': timestamp + 60, 'jti': str(uuid.uuid4())}
    header = {'alg': algorithm, 'typ': 'JWT'}
    unsigned = '.'.join(b64(json.dumps(part, separators=(',', ':')).encode()) for part in (header, claims)).encode()
    if isinstance(key, rsa.RSAPrivateKey):
        signature = key.sign(unsigned, padding.PKCS1v15(), digest)
    else:
        r, s = decode_dss_signature(key.sign(unsigned, ec.ECDSA(digest)))
        size = (key.key_size + 7) // 8
        signature = r.to_bytes(size, 'big') + s.to_bytes(size, 'big')
    return unsigned.decode() + '.' + b64(signature)


def checked_json(response):
    if response.status_code in (401, 403):
        raise HTTPException(502, 'Operator odrzucił uwierzytelnienie lub dostęp. Sprawdź ADE, nazwę systemu, certyfikat i uprawnienia w skrzynce.')
    if response.status_code == 429:
        raise HTTPException(503, 'Limit zapytań eDoręczeń został przekroczony. Spróbuj później.')
    if response.status_code != 200:
        raise HTTPException(502, 'Usługa eDoręczeń nie wykonała operacji. Spróbuj później lub sprawdź konfigurację systemu.')
    try:
        return response.json()
    except ValueError:
        raise HTTPException(502, 'Operator zwrócił niepoprawną odpowiedź eDoręczeń.') from None


class MailboxClient:
    def __init__(self, config, data):
        self.config, self.data = config, data
        self.http = httpx.Client(timeout=20, follow_redirects=False)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.http.close()

    def authenticate(self):
        try:
            payload = checked_json(self.http.post(TOKEN_URL, params={'login_hint': 'ADE.' + self.config['address']}, data={
                'grant_type': 'client_credentials', 'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
                'client_assertion': assertion(self.config, self.data)}))
            token = payload.get('access_token') if isinstance(payload, dict) else None
            if not isinstance(token, str) or not token or any(ord(c) < 32 for c in token):
                raise HTTPException(502, 'Operator nie zwrócił tokena dostępu.')
            self.http.headers['Authorization'] = 'Bearer ' + token
        except httpx.HTTPError:
            raise HTTPException(502, 'Nie można połączyć się z usługą uwierzytelnienia eDoręczeń.') from None

    def page(self, offset=0, limit=100):
        try:
            result = checked_json(self.http.get(API_URL + '/' + quote(self.config['address'], safe='') + '/messages',
                params={'format': 'metadata', 'offset': offset, 'limit': limit, 'sortColumn': 'timestamp', 'sortDirection': 'desc', 'shippingService': 'electronic'}))
            if not isinstance(result, dict) or not isinstance(result.get('messages'), list):
                raise HTTPException(502, 'Operator zwrócił niepoprawną listę przesyłek.')
            if any(not isinstance(item, dict) for item in result['messages']):
                raise HTTPException(502, 'Operator zwrócił niepoprawną listę przesyłek.')
            return result
        except httpx.HTTPError:
            raise HTTPException(502, 'Nie można pobrać listy przesyłek ze skrzynki eDoręczeń.') from None


def metadata_record(message, address):
    try:
        meta, control = message['messageMetadata'], message.get('messageControlData') or {}
        message_id = meta['messageId']
        if not isinstance(message_id, str) or not message_id or len(message_id) > 200:
            raise ValueError()
        sender = meta.get('from') or {}
        outgoing = sender.get('eDeliveryAddress') == address
        parties = (meta.get('to') or []) if outgoing else [sender]
        names, addresses = [], []
        for party in parties:
            contributor = party.get('contributor') or {}
            ade = party.get('eDeliveryAddress') or ''
            name = contributor.get('companyName') or ' '.join(filter(None, (contributor.get('firstName'), contributor.get('lastName')))) or ade
            if name: names.append(name)
            if ade: addresses.append(ade)
        remote_status = control.get('status') or 'Brak statusu'
        status = {'Doręczona': 'delivered', 'Uznana za doręczoną': 'delivered', 'Niedoręczona': 'failed', 'Odrzucona': 'failed', 'Nadana': 'sent', 'Wysłana': 'sent'}.get(remote_status, 'registered')
        timestamp = meta.get('receiptDate') or meta.get('submissionDate') or meta.get('timestamp')
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        if parsed.tzinfo is None: raise ValueError()
        day = parsed.astimezone(ZoneInfo('Europe/Warsaw')).date().isoformat()
        return {'message_id': message_id, 'remote_status': remote_status[:200], 'title': (meta.get('subject') or 'Przesyłka bez tematu')[:200],
                'correspondent': ('; '.join(names) or 'Brak danych korespondenta')[:200], 'address': '; '.join(addresses)[:200],
                'reference': message_id, 'direction': 'outgoing' if outgoing else 'incoming', 'status': status, 'record_date': day}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise HTTPException(502, 'Niepoprawne metadane przesyłki od operatora. Rejestr nie został zmieniony.') from None


def install(app, db, user, now):
    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        if request.url.path.startswith('/api/edeliveries/connection'):
            return JSONResponse(status_code=422, content={'detail': [
                {'loc': item['loc'], 'type': item['type'], 'msg': item['msg']}
                for item in error.errors()]})
        return await request_validation_exception_handler(request, error)

    @app.get('/api/edeliveries/connection')
    def settings(current=Depends(user)):
        with db() as con:
            row = con.execute('SELECT * FROM edelivery_connections WHERE user_id=?', (current['id'],)).fetchone()
            return public_settings(row)

    @app.put('/api/edeliveries/connection')
    def save(body: ConnectionInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = con.execute('SELECT * FROM edelivery_connections WHERE user_id=?', (current['id'],)).fetchone()
            if body.version != (row['version'] if row else 0):
                raise HTTPException(409, 'Konfiguracja została zmieniona. Otwórz ustawienia ponownie.')
            data = stored_secrets(row) if row else {'certificate': '', 'private_key': '', 'key_password': ''}
            if body.certificate: data['certificate'] = body.certificate.strip()
            if body.private_key:
                data['private_key'] = body.private_key.strip()
                data['key_password'] = body.key_password or ''
            elif body.key_password is not None:
                data['key_password'] = body.key_password
            if data['certificate'] and data['private_key'] and (body.enabled or body.certificate or body.private_key or body.key_password is not None):
                private_material(data)
            if body.enabled and not (body.address and body.system_name and data['certificate'] and data['private_key']):
                raise HTTPException(422, 'Uzupełnij ADE, nazwę systemu, certyfikat i klucz prywatny przed włączeniem połączenia.')
            config = {'enabled': body.enabled, 'address': body.address, 'system_name': body.system_name,
                      'has_certificate': bool(data['certificate']), 'has_private_key': bool(data['private_key'])}
            encrypted = cipher().encrypt(json.dumps(data).encode()).decode()
            con.execute('''INSERT INTO edelivery_connections(user_id,config,secrets) VALUES(?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET config=excluded.config,secrets=excluded.secrets,version=edelivery_connections.version+1''',
                (current['id'], json.dumps(config), encrypted))
            return public_settings(con.execute('SELECT * FROM edelivery_connections WHERE user_id=?', (current['id'],)).fetchone())

    @app.delete('/api/edeliveries/connection', status_code=204)
    def disconnect(current=Depends(user)):
        with db() as con:
            con.begin_write()
            con.execute('DELETE FROM edelivery_connections WHERE user_id=?', (current['id'],))
        return Response(status_code=204)

    @app.post('/api/edeliveries/connection/test')
    def test(current=Depends(user)):
        with db() as con: config, data = load_connection(con, current)
        with MailboxClient(config, data) as client:
            client.authenticate()
            client.page(limit=1)
        return {'message': 'Połączenie i dostęp do listy przesyłek działają. Nie otwarto ani nie wysłano żadnej przesyłki.'}

    @app.post('/api/edeliveries/sync')
    def sync(current=Depends(user)):
        with db() as con:
            config, data = load_connection(con, current)
            connection_version = config['version']
        imported, more = [], False
        with MailboxClient(config, data) as client:
            client.authenticate()
            for offset in range(0, 500, 100):
                result = client.page(offset, 100)
                messages = result['messages']
                if len(messages) > 100: raise HTTPException(502, 'Operator zwrócił zbyt dużą stronę przesyłek.')
                for message in messages:
                    control = message.get('messageControlData') or {}
                    if not isinstance(control, dict):
                        raise HTTPException(502, 'Operator zwrócił niepoprawne metadane przesyłki.')
                    if control.get('messageType', 'Message') == 'Message':
                        imported.append(metadata_record(message, config['address']))
                if len(messages) < 100: break
                more = offset == 400
        added = updated = 0
        timestamp = now()
        with db() as con:
            con.begin_write()
            current_row = con.execute('SELECT version FROM edelivery_connections WHERE user_id=?', (current['id'],)).fetchone()
            if not current_row or current_row['version'] != connection_version:
                raise HTTPException(409, 'Konfiguracja zmieniła się podczas synchronizacji. Spróbuj ponownie.')
            for item in imported:
                mapping = con.execute('SELECT record_id FROM edelivery_imports WHERE user_id=? AND mailbox_address=? AND message_id=?',
                    (current['id'], config['address'], item['message_id'])).fetchone()
                values = tuple(item[key] for key in ('title', 'correspondent', 'address', 'reference', 'direction', 'status', 'record_date'))
                if mapping:
                    con.execute('''UPDATE edelivery_records SET title=?,correspondent=?,address=?,reference=?,direction=?,status=?,record_date=?,updated_at=?,version=version+1 WHERE id=? AND user_id=?''', (*values, timestamp, mapping['record_id'], current['id']))
                    con.execute('UPDATE edelivery_imports SET remote_status=?,synced_at=? WHERE record_id=?', (item['remote_status'], timestamp, mapping['record_id']))
                    updated += 1
                else:
                    identifier = secrets.token_hex(16)
                    con.execute('''INSERT INTO edelivery_records(id,user_id,title,correspondent,address,reference,direction,status,record_date,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (identifier, current['id'], *values, '', timestamp, timestamp))
                    con.execute('INSERT INTO edelivery_imports(record_id,user_id,mailbox_address,message_id,remote_status,synced_at) VALUES(?,?,?,?,?,?)',
                        (identifier, current['id'], config['address'], item['message_id'], item['remote_status'], timestamp))
                    added += 1
        return {'added': added, 'updated': updated, 'more': more, 'message': f'Synchronizacja metadanych: dodano {added}, zaktualizowano {updated}. Zakres: do 500 najnowszych przesyłek.'}
