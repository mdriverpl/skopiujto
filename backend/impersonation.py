"""Short-lived customer sessions attached to the superadministrator's browser session."""
import secrets
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request, Response
from backend import admin

COOKIE = 'customer_session'
STOP_PATH = '/api/admin/impersonation/stop'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS impersonation_sessions(
 token TEXT PRIMARY KEY, actor_session TEXT NOT NULL UNIQUE REFERENCES sessions(token) ON DELETE CASCADE,
 actor_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 target_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS impersonation_events(
 id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, actor_name TEXT NOT NULL,
 target_id TEXT NOT NULL, target_name TEXT NOT NULL, company_id TEXT NOT NULL,
 action TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS impersonation_events_time ON impersonation_events(created_at);
'''


def event(con, actor, target, action):
    con.execute('INSERT INTO impersonation_events(id,actor_id,actor_name,target_id,target_name,company_id,action,created_at) VALUES(?,?,?,?,?,?,?,?)',
        (secrets.token_hex(16), actor['id'], actor['name'], target['id'], target['name'], target['company_id'], action, datetime.now(timezone.utc).isoformat()))


def resolve(con, request, actor, actor_session, digest):
    request.state.impersonation_expired = False
    token = request.cookies.get(COOKIE)
    if not token or (request.url.path == STOP_PATH and request.method == 'POST'):
        return actor, None
    row = con.execute('SELECT * FROM impersonation_sessions WHERE token=? AND actor_session=? AND actor_id=?',
                      (digest(token), actor_session, actor['id'])).fetchone()
    target = con.execute('SELECT u.*,co.name AS company_name FROM users u JOIN companies co ON co.id=u.company_id WHERE u.id=?',
                         (row['target_id'],)).fetchone() if row else None
    if not row or row['expires'] <= datetime.now(timezone.utc).timestamp() or not actor['is_superadmin'] or not target or not target['active'] or target['is_superadmin']:
        if request.url.path == '/api/me' and request.method == 'GET':
            request.state.impersonation_expired = True
            if row:
                if target: event(con, actor, target, 'Wygasł tryb klienta')
                con.execute('DELETE FROM impersonation_sessions WHERE token=?', (row['token'],))
            return actor, None
        raise HTTPException(409, 'Tryb klienta wygasł lub został cofnięty. Wróć na konto superadministratora albo odśwież stronę.')
    info = {'actor_id': actor['id'], 'actor_name': actor['name'],
            'expires': datetime.fromtimestamp(row['expires'], timezone.utc).isoformat(),
            'requires_password_change': bool(target['must_change_password'])}
    return target, info


def install(app, db, user, digest, secure_cookie):
    def browser_user(request: Request, current=Depends(user)):
        if getattr(request.state, 'api_token', False):
            raise HTTPException(403, 'Wejście na konto klienta wymaga sesji przeglądarki, nie klucza API.')
        return current

    @app.post('/api/admin/users/{target_id}/impersonate')
    def start(target_id: str, request: Request, response: Response, current=Depends(browser_user)):
        if current.get('impersonation'):
            raise HTTPException(409, 'Najpierw wróć na własne konto.')
        if not current.get('is_superadmin'):
            raise HTTPException(403, 'Tylko superadministrator może wejść na konto klienta.')
        actor_session = digest(request.cookies.get('session', ''))
        with db() as con:
            con.begin_write()
            actor = con.execute('SELECT * FROM users WHERE id=? AND active=1 AND is_superadmin=1', (current['id'],)).fetchone()
            parent = con.execute('SELECT * FROM sessions WHERE token=? AND user_id=? AND expires>?',
                (actor_session, current['id'], datetime.now(timezone.utc).timestamp())).fetchone()
            if not actor or not parent: raise HTTPException(401, 'Zaloguj się ponownie na konto superadministratora.')
            target = con.execute('SELECT u.*,co.name AS company_name FROM users u JOIN companies co ON co.id=u.company_id WHERE u.id=?', (target_id,)).fetchone()
            if not target: raise HTTPException(404, 'Nie znaleziono konta klienta.')
            if not target['active'] or target['is_superadmin'] or target['id'] == current['id']:
                raise HTTPException(409, 'Wybierz aktywne konto klienta inne niż konto superadministratora.')
            token = secrets.token_urlsafe(32)
            expires = min(parent['expires'], datetime.now(timezone.utc).timestamp() + 1800)
            con.execute('DELETE FROM impersonation_sessions WHERE actor_session=? OR expires<?', (actor_session, datetime.now(timezone.utc).timestamp()))
            con.execute('INSERT INTO impersonation_sessions VALUES(?,?,?,?,?)', (digest(token), actor_session, current['id'], target_id, expires))
            event(con, actor, target, 'Wejście na konto klienta')
        response.set_cookie(COOKIE, token, httponly=True, secure=secure_cookie, samesite='lax', max_age=max(1, int(expires-datetime.now(timezone.utc).timestamp())))
        return {'target_id': target_id, 'target_name': target['name'], 'expires': datetime.fromtimestamp(expires, timezone.utc).isoformat()}

    @app.post(STOP_PATH)
    def stop(request: Request, response: Response, current=Depends(browser_user)):
        actor_session = digest(request.cookies.get('session', ''))
        with db() as con:
            con.begin_write()
            row = con.execute('SELECT * FROM impersonation_sessions WHERE actor_session=? AND actor_id=?', (actor_session, current['id'])).fetchone()
            if row:
                target = con.execute('SELECT * FROM users WHERE id=?', (row['target_id'],)).fetchone()
                if target: event(con, current, target, 'Powrót na konto administratora')
                con.execute('DELETE FROM impersonation_sessions WHERE actor_session=?', (actor_session,))
        response.delete_cookie(COOKIE)
        return {'returned': True}

    @app.get('/api/admin/impersonation/events')
    def history(current=Depends(browser_user)):
        if not current.get('is_superadmin') or current.get('impersonation'):
            raise HTTPException(403, 'Historia wejść jest dostępna tylko na koncie superadministratora.')
        with db() as con:
            return [dict(row) for row in con.execute('SELECT e.*,c.name AS company_name FROM impersonation_events e LEFT JOIN companies c ON c.id=e.company_id ORDER BY e.created_at DESC,e.id DESC LIMIT 100')]
