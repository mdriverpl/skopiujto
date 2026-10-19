"""Account-scoped Web Push with persistent deduplication and retries."""
import base64
import hashlib
import json
import logging
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger(__name__)
SCHEMA = '''
CREATE TABLE IF NOT EXISTS push_subscriptions(
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
 session_token TEXT NOT NULL REFERENCES sessions(token) ON DELETE CASCADE,
 endpoint TEXT NOT NULL UNIQUE,subscription TEXT NOT NULL,name TEXT NOT NULL,
 messages INTEGER NOT NULL DEFAULT 1,tasks INTEGER NOT NULL DEFAULT 1,
 reminders INTEGER NOT NULL DEFAULT 1,created_at DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS push_subscriptions_user ON push_subscriptions(user_id);
CREATE TABLE IF NOT EXISTS push_deliveries(
 subscription_id TEXT NOT NULL REFERENCES push_subscriptions(id) ON DELETE CASCADE,
 event_key TEXT NOT NULL,payload TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt DOUBLE PRECISION NOT NULL,sent_at DOUBLE PRECISION,
 PRIMARY KEY(subscription_id,event_key));
'''


def stamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
    except (ValueError, TypeError, AttributeError):
        return 0


def configuration():
    return tuple(os.getenv('EDOCUMENTS_WEBPUSH_' + key, '') for key in ('PRIVATE_KEY', 'PUBLIC_KEY', 'SUBJECT'))


def configured():
    return all(configuration())


class Preferences(BaseModel):
    messages: bool = True
    tasks: bool = True
    reminders: bool = True


class DeviceSettings(Preferences):
    name: str | None = Field(default=None, min_length=1, max_length=80)


class SubscriptionInput(Preferences):
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: dict[str, str]
    name: str = Field(default='Moje urządzenie', min_length=1, max_length=80)

    @field_validator('endpoint')
    @classmethod
    def trusted_endpoint(cls, value):
        # Prevent arbitrary server-side HTTP requests (SSRF).
        parsed = urlsplit(value)
        trusted = parsed.hostname in {
            'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'
        } or bool(parsed.hostname and parsed.hostname.endswith('.notify.windows.com'))
        if (parsed.scheme != 'https' or not trusted or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.fragment):
            raise ValueError('Nieobsługiwany adres usługi push.')
        return value

    @field_validator('keys')
    @classmethod
    def valid_keys(cls, value):
        try:
            public = base64.urlsafe_b64decode(value['p256dh'] + '===')
            auth = base64.urlsafe_b64decode(value['auth'] + '===')
            if len(public) != 65 or len(auth) != 16:
                raise ValueError()
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
        except (KeyError, ValueError, TypeError):
            raise ValueError('Nieprawidłowe klucze subskrypcji push.') from None
        return {key: value[key] for key in ('p256dh', 'auth')}


def active(con, now):
    return con.execute('''SELECT p.* FROM push_subscriptions p
        JOIN sessions s ON s.token=p.session_token AND s.user_id=p.user_id
        JOIN users u ON u.id=p.user_id
        WHERE s.expires>? AND u.active=1 AND u.deleted_at IS NULL AND u.must_change_password=0''', (now,)).fetchall()


def events(con, subscription, now):
    result, owner = {}, subscription['user_id']

    def add(key, title, body, section):
        # No private contents or document titles on the lock screen.
        result[key] = {'title': title, 'body': body, 'tag': hashlib.sha256(key.encode()).hexdigest()[:32],
                       'url': '/?section=' + section}

    if subscription['messages']:
        for row in con.execute('SELECT id,created_at FROM user_messages WHERE recipient_id=? AND read_at IS NULL', (owner,)):
            if subscription['created_at'] <= stamp(row['created_at']) <= now:
                add('message:' + row['id'], 'Nowa wiadomość', 'Masz nową wiadomość w eDokumentach.', 'mail')
        for row in con.execute('''SELECT id,created_at FROM client_mail
                WHERE user_id=? AND folder='inbox' AND category!='spam' AND unread=1''', (owner,)):
            if subscription['created_at'] <= stamp(row['created_at']) <= now:
                add('email:' + row['id'], 'Nowy e-mail', 'Nowa wiadomość czeka w Twojej skrzynce.', 'mail')
    for row in con.execute("SELECT id,created_at,due_at FROM user_tasks WHERE assignee_id=? AND status IN ('todo','in_progress')", (owner,)):
        if subscription['tasks'] and subscription['created_at'] <= stamp(row['created_at']) <= now:
            add('task:' + row['id'], 'Nowe zadanie', 'Przydzielono Ci zadanie w eDokumentach.', 'tasks')
        if subscription['reminders'] and 0 < stamp(row['due_at']) - now <= 86400:
            window = '1h' if stamp(row['due_at']) - now <= 3600 else '24h'
            add('task-due:' + row['id'] + ':' + str(row['due_at']) + ':' + window, 'Zbliża się termin zadania',
                'Sprawdź zadania na najbliższą godzinę.' if window == '1h' else 'Sprawdź zadania na najbliższe 24 godziny.', 'tasks')
    if subscription['reminders']:
        for row in con.execute('''SELECT d.id,d.due_at FROM deadlines d JOIN documents doc ON doc.id=d.document_id
                WHERE doc.user_id=? AND d.done=0''', (owner,)):
            if 0 < stamp(row['due_at']) - now <= 86400:
                window = '1h' if stamp(row['due_at']) - now <= 3600 else '24h'
                add('deadline:' + row['id'] + ':' + row['due_at'] + ':' + window, 'Zbliża się termin',
                    'Sprawdź terminarz na najbliższą godzinę.' if window == '1h' else 'Sprawdź terminarz na najbliższe 24 godziny.', 'calendar')
    return result


def send(subscription, payload):
    from pywebpush import webpush
    private, _, subject = configuration()
    return webpush(subscription_info=json.loads(subscription['subscription']), data=json.dumps(payload),
                   vapid_private_key=private, vapid_claims={'sub': subject}, ttl=3600, timeout=10)


def dispatch(db, now=None):
    if not configured():
        return
    timestamp = time.time() if now is None else now
    with db() as con:
        subscriptions = active(con, timestamp)
    for subscription in subscriptions:
        timestamp = time.time() if now is None else now
        with db() as con:
            con.begin_write()
            if not any(row['id'] == subscription['id'] for row in active(con, timestamp)):
                continue
            candidates = events(con, subscription, timestamp)
            for key, payload in candidates.items():
                con.execute('''INSERT INTO push_deliveries(subscription_id,event_key,payload,next_attempt)
                    VALUES(?,?,?,?) ON CONFLICT DO NOTHING''', (subscription['id'], key, json.dumps(payload), timestamp))
            pending = con.execute('''SELECT * FROM push_deliveries WHERE subscription_id=?
                AND sent_at IS NULL AND next_attempt<=? AND attempts<8 ORDER BY next_attempt,event_key LIMIT 10''',
                (subscription['id'], timestamp)).fetchall()
            work = []
            for delivery in pending:
                if delivery['event_key'] not in candidates:
                    con.execute('DELETE FROM push_deliveries WHERE subscription_id=? AND event_key=?',
                                (subscription['id'], delivery['event_key']))
                    continue
                # Lease outlives a bounded batch; another process will not claim the same work.
                con.execute('''UPDATE push_deliveries SET attempts=attempts+1,next_attempt=?
                    WHERE subscription_id=? AND event_key=?''', (timestamp + 300, subscription['id'], delivery['event_key']))
                work.append(delivery)
        for delivery in work:
            timestamp = time.time() if now is None else now
            with db() as con:
                fresh = next((row for row in active(con, timestamp) if row['id'] == subscription['id']), None)
                valid = fresh and delivery['event_key'] in events(con, fresh, timestamp)
            if not valid:
                continue
            try:
                send(fresh, json.loads(delivery['payload']))
            except Exception as exc:
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                with db() as con:
                    if status in (404, 410):
                        con.execute('DELETE FROM push_subscriptions WHERE id=?', (subscription['id'],))
                    else:
                        con.execute('UPDATE push_deliveries SET next_attempt=? WHERE subscription_id=? AND event_key=?',
                            (timestamp + min(3600, 60 * 2 ** delivery['attempts']), subscription['id'], delivery['event_key']))
                log.warning('Web Push delivery failed (provider status: %s)', status or 'unavailable')
                if status in (404, 410):
                    break
            else:
                with db() as con:
                    con.execute('UPDATE push_deliveries SET sent_at=? WHERE subscription_id=? AND event_key=?',
                                (timestamp, subscription['id'], delivery['event_key']))


def install(app, db, user):
    def browser(request: Request, current=Depends(user)):
        if current.get('impersonation') or getattr(request.state, 'api_token', False):
            raise HTTPException(403, 'Zarządzaj powiadomieniami po zalogowaniu na własne konto w przeglądarce.')
        return current

    @app.get('/api/push/config')
    def config(current=Depends(browser)):
        return {'configured': configured(), 'public_key': configuration()[1] if configured() else ''}

    @app.get('/api/push/subscriptions')
    def listing(current=Depends(browser)):
        with db() as con:
            return [{key: row[key] for key in ('id', 'name', 'messages', 'tasks', 'reminders', 'created_at')}
                    for row in active(con, time.time()) if row['user_id'] == current['id']]

    @app.post('/api/push/subscriptions', status_code=201)
    def subscribe(body: SubscriptionInput, request: Request, current=Depends(browser)):
        if not configured():
            raise HTTPException(503, 'Administrator musi skonfigurować klucze Web Push na serwerze.')
        session_hash = hashlib.sha256(request.cookies.get('session', '').encode()).hexdigest()
        with db() as con:
            con.begin_write()
            if not con.execute('SELECT 1 FROM sessions WHERE token=? AND user_id=? AND expires>?',
                               (session_hash, current['id'], time.time())).fetchone():
                raise HTTPException(401, 'Zaloguj się ponownie.')
            existing = con.execute('SELECT * FROM push_subscriptions WHERE endpoint=?', (body.endpoint,)).fetchone()
            if existing and existing['user_id'] != current['id']:
                raise HTTPException(409, 'Ta przeglądarka ma powiadomienia innego konta. Wyłącz je przed zmianą konta.')
            identifier = existing['id'] if existing else secrets.token_hex(16)
            con.execute('''INSERT INTO push_subscriptions(id,user_id,session_token,endpoint,subscription,name,messages,tasks,reminders,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(endpoint) DO UPDATE SET session_token=excluded.session_token,
                subscription=excluded.subscription,name=excluded.name,messages=excluded.messages,tasks=excluded.tasks,reminders=excluded.reminders''',
                (identifier, current['id'], session_hash, body.endpoint,
                 json.dumps({'endpoint': body.endpoint, 'keys': body.keys}), body.name.strip() or 'Moje urządzenie',
                 body.messages, body.tasks, body.reminders, time.time()))
        return {'id': identifier}

    @app.patch('/api/push/subscriptions/{identifier}')
    def preferences(identifier: str, body: DeviceSettings, current=Depends(browser)):
        with db() as con:
            if not con.execute('SELECT 1 FROM push_subscriptions WHERE id=? AND user_id=?', (identifier, current['id'])).fetchone():
                raise HTTPException(404, 'Nie znaleziono urządzenia.')
            con.execute('UPDATE push_subscriptions SET messages=?,tasks=?,reminders=?,name=coalesce(?,name) WHERE id=?',
                        (body.messages, body.tasks, body.reminders, body.name.strip() if body.name else None, identifier))
        return {'saved': True}

    @app.delete('/api/push/subscriptions/{identifier}', status_code=204)
    def remove(identifier: str, current=Depends(browser)):
        with db() as con:
            con.execute('DELETE FROM push_subscriptions WHERE id=? AND user_id=?', (identifier, current['id']))

    @app.post('/api/push/subscriptions/{identifier}/test')
    def test_push(identifier: str, current=Depends(browser)):
        if not configured():
            raise HTTPException(503, 'Web Push nie jest jeszcze skonfigurowany.')
        with db() as con:
            subscription = next((row for row in active(con, time.time())
                                 if row['id'] == identifier and row['user_id'] == current['id']), None)
        if not subscription:
            raise HTTPException(404, 'Nie znaleziono urządzenia.')
        try:
            send(subscription, {'title': 'eDokumenty', 'body': 'Powiadomienia na tym urządzeniu działają.',
                                'tag': 'edokumenty-test', 'url': '/'})
        except Exception:
            raise HTTPException(503, 'Nie udało się wysłać testu. Sprawdź konfigurację i włącz powiadomienia ponownie.') from None
        return {'sent': True}

    stop = threading.Event()
    worker = None

    def loop():
        while not stop.wait(30):
            try:
                dispatch(db)
            except Exception:
                log.warning('Web Push dispatcher unavailable; retrying in 30 seconds')

    def startup():
        nonlocal worker
        stop.clear()
        if configured() and os.getenv('EDOCUMENTS_WEBPUSH_WORKER', '1') == '1':
            worker = threading.Thread(target=loop, name='webpush', daemon=True)
            worker.start()

    def shutdown():
        stop.set()
        if worker:
            worker.join(timeout=1)

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application) as state:
            startup()
            try:
                yield state
            finally:
                shutdown()

    app.router.lifespan_context = lifespan
