import hashlib
import hmac
import json
import os
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, APIKeyCookie
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool
from backend import storage, access, admin, images, mailing, workflow, richtext, ai, document_fields, ai_files, saved_data, tasks, dictionaries, dictionary_excel, ai_commands, surveys, audit
from backend import database, api_tokens, assistant, notes, flows, client_mail, mail_settings, mail_daily, edelivery, edelivery_connection, companies, impersonation
from backend import message_center, webpush, folder_archive, external_shares
from backend.pricing_offer import router as pricing_router

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
DATABASE_URL = os.getenv('DATABASE_URL', '')
SECURE_COOKIE = os.getenv('EDOCUMENTS_SECURE_COOKIE', '0') == '1'
MAX_UPLOAD = 10 * 1024 * 1024
app = FastAPI(title='Space & Flow — eDokumenty REST API', version='1.1.0',
    description='API dokumentów, folderów, historii, zadań i ankiet. Logowanie przeglądarki używa cookie session. Integracje używają nagłówka Authorization: Bearer <klucz API>.',
    docs_url='/api/docs', redoc_url='/api/redoc', openapi_url='/api/openapi.json')
bearer_auth = HTTPBearer(auto_error=False, scheme_name='ApiKeyBearer')
app.include_router(pricing_router)
cookie_auth = APIKeyCookie(name='session', auto_error=False, scheme_name='BrowserSession')

@contextmanager
def db():
    with database.connect(DATABASE_URL) as con:
        yield con

def initialize():
    with db() as c:
        c.begin_write()
        c.ensure_schema()
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT NOT NULL, password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS folders(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
          name TEXT NOT NULL, parent_id TEXT REFERENCES folders(id) ON DELETE RESTRICT, created_at TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS folder_names ON folders(user_id,coalesce(parent_id,''),lower(name));
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires DOUBLE PRECISION NOT NULL);
        CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
          category TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          version INTEGER NOT NULL DEFAULT 1, filename TEXT, file BYTEA);
        CREATE TABLE IF NOT EXISTS comments(id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
          author TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS deadlines(id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
          title TEXT NOT NULL, due_at TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS shares(id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
          expires DOUBLE PRECISION NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS templates(id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), title TEXT NOT NULL,
          category TEXT NOT NULL, description TEXT NOT NULL, content TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS deleted_default_templates(id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS groups(id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS group_members(group_id TEXT REFERENCES groups(id) ON DELETE CASCADE,
          user_id TEXT REFERENCES users(id), PRIMARY KEY(group_id,user_id));
        CREATE TABLE IF NOT EXISTS group_permissions(group_id TEXT REFERENCES groups(id) ON DELETE CASCADE,
          scope TEXT NOT NULL, folder_id TEXT REFERENCES folders(id) ON DELETE CASCADE,
          can_read INTEGER NOT NULL, can_edit INTEGER NOT NULL, can_add INTEGER NOT NULL, can_delete INTEGER NOT NULL,
          PRIMARY KEY(group_id,scope));
        CREATE TABLE IF NOT EXISTS folder_user_permissions(folder_id TEXT REFERENCES folders(id) ON DELETE CASCADE,
          user_id TEXT REFERENCES users(id), can_read INTEGER NOT NULL, can_edit INTEGER NOT NULL,
          can_add INTEGER NOT NULL, can_delete INTEGER NOT NULL, PRIMARY KEY(folder_id,user_id));
        ''')
        c.executescript(mailing.SCHEMA)
        mailing.migrate(c)
        c.executescript(saved_data.SCHEMA)
        c.executescript(notes.SCHEMA)
        c.executescript(edelivery.SCHEMA)
        c.executescript(edelivery_connection.SCHEMA)
        client_mail.initialize(c)
        c.executescript(mail_settings.SCHEMA)
        tasks.initialize(c)
        dictionaries.initialize(c)
        c.executescript(client_mail.mail_rules.SCHEMA)
        c.executescript(ai_commands.SCHEMA)
        c.executescript(message_center.SCHEMA)
        c.executescript(webpush.SCHEMA)
        c.executescript(external_shares.SCHEMA)
        c.executescript(surveys.SCHEMA)
        if 'scoring_profile' not in c.columns('surveys'):
            c.execute("ALTER TABLE surveys ADD COLUMN scoring_profile TEXT NOT NULL DEFAULT ''")
        c.executescript(audit.SCHEMA)
        c.executescript(api_tokens.SCHEMA)
        folder_columns = c.columns('folders')
        if 'access_mode' not in folder_columns:
            c.execute("ALTER TABLE folders ADD COLUMN access_mode TEXT NOT NULL DEFAULT 'inherit'")
        user_columns = c.columns('users')
        for name, kind in [('role', "TEXT NOT NULL DEFAULT 'user'"), ('active', 'INTEGER NOT NULL DEFAULT 1'),
                           ('can_read', 'INTEGER NOT NULL DEFAULT 1'), ('can_edit', 'INTEGER NOT NULL DEFAULT 1'),
                           ('can_add', 'INTEGER NOT NULL DEFAULT 1'), ('can_delete', 'INTEGER NOT NULL DEFAULT 1'),
                           ('email', 'TEXT'), ('deleted_at', 'TEXT'), ('must_change_password', 'INTEGER NOT NULL DEFAULT 0'),
                           ('menu_order', "TEXT NOT NULL DEFAULT '[]'")]:
            if name not in user_columns:
                c.execute(f'ALTER TABLE users ADD COLUMN {name} {kind}')
        if 'role' not in user_columns:
            c.execute("UPDATE users SET role='admin' WHERE id=(SELECT id FROM users ORDER BY id LIMIT 1)")
        companies.initialize(c)
        c.executescript(flows.SCHEMA)
        c.executescript(impersonation.SCHEMA)
        if 'read_only' not in c.columns('impersonation_sessions'):
            c.execute('ALTER TABLE impersonation_sessions ADD COLUMN read_only INTEGER NOT NULL DEFAULT 0')
        columns = c.columns('documents')
        for name, kind in [('object_key', 'TEXT'), ('object_bucket', 'TEXT'), ('file_size', 'INTEGER'),
                           ('folder_id', 'TEXT REFERENCES folders(id) ON DELETE RESTRICT'),
                           ('uploaded_by', 'TEXT REFERENCES users(id)'), ('rich_content', 'TEXT'), ('field_source', 'TEXT'), ('field_values', 'TEXT')]:
            if name not in columns:
                c.execute(f'ALTER TABLE documents ADD COLUMN {name} {kind}')
        c.execute('UPDATE documents SET uploaded_by=user_id WHERE filename IS NOT NULL AND uploaded_by IS NULL')
        template_columns = c.columns('templates')
        for name, kind in [('rich_content', 'TEXT'), ('version', 'INTEGER NOT NULL DEFAULT 1')]:
            if name not in template_columns:
                c.execute(f'ALTER TABLE templates ADD COLUMN {name} {kind}')
        for t in DEFAULT_TEMPLATES:
            if c.execute('SELECT 1 FROM deleted_default_templates WHERE id=?', (t['id'],)).fetchone():
                continue
            c.execute('INSERT INTO templates(id,user_id,title,category,description,content) VALUES(?,NULL,?,?,?,?) ON CONFLICT DO NOTHING', (t['id'],t['title'],t['category'],t['description'],t['content']))

DEFAULT_TEMPLATES = [
    dict(id='agreement', title='Umowa o współpracy', category='Umowy', description='Warunki współpracy, zakres i wynagrodzenie.', content='UMOWA O WSPÓŁPRACY\n\nZawarta w dniu [data] w [miejscowość] pomiędzy:\n[nazwa i adres strony A]\na\n[nazwa i adres strony B]\n\n§ 1. Przedmiot umowy\n[Opisz zakres współpracy]\n\n§ 2. Wynagrodzenie\n[Kwota i warunki płatności]\n\n§ 3. Termin realizacji\n[Data rozpoczęcia i zakończenia]\n\n§ 4. Postanowienia końcowe\n[Uzupełnij ustalenia]\n\nPodpisy stron:\n________________    ________________'),
    dict(id='minutes', title='Protokół spotkania', category='Protokoły', description='Uczestnicy, ustalenia i kolejne kroki.', content='PROTOKÓŁ SPOTKANIA\n\nData: [data]\nUczestnicy: [imiona i nazwiska]\nTemat: [temat spotkania]\n\n1. Omówione zagadnienia\n[Opis]\n\n2. Podjęte decyzje\n[Decyzje]\n\n3. Zadania i terminy\n[Zadanie — osoba odpowiedzialna — termin]\n\nSporządził/a: [imię i nazwisko]'),
    dict(id='letter', title='Pismo ogólne', category='Pisma', description='Uniwersalny wzór oficjalnego pisma.', content='[Miejscowość], [data]\n\nNadawca:\n[Imię i nazwisko / firma]\n[Adres]\n\nAdresat:\n[Nazwa odbiorcy]\n[Adres]\n\nDotyczy: [temat]\n\nSzanowni Państwo,\n\n[Treść pisma]\n\nZ poważaniem,\n[Podpis]'),
    dict(id='offer', title='Oferta usług', category='Oferty', description='Zakres prac, cena i ważność oferty.', content='OFERTA USŁUG\n\nDla: [klient]\nData: [data]\n\nZakres usług\n[Opis proponowanych prac]\n\nHarmonogram\n[Etapy i terminy]\n\nWycena\n[Pozycja — ilość — cena]\n\nWarunki płatności\n[Warunki]\n\nOferta ważna do: [data]\nKontakt: [dane kontaktowe]'),
]
initialize()

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f'{salt}:{value}'

@app.middleware('http')
async def security_headers(request: Request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin = request.headers.get('origin')
        allowed = {str(request.base_url).rstrip('/'),
                   'http://localhost:5173', 'http://127.0.0.1:5173',
                   'http://localhost:5174', 'http://127.0.0.1:5174'}
        from urllib.parse import urlsplit
        try:
            public_url = urlsplit(os.getenv('EDOCUMENTS_PUBLIC_URL', ''))
        except ValueError:
            public_url = urlsplit('')
        if public_url.scheme in ('http', 'https') and public_url.netloc:
            allowed.add(public_url.scheme + '://' + public_url.netloc)
        if origin and origin not in allowed:
            return Response('Niedozwolone źródło żądania', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    if request.url.path.startswith(('/api','/share','/accept','/public-share')):
        response.headers['Cache-Control'] = 'no-store'
    return response

def user(request: Request, bearer=Depends(bearer_auth), cookie=Depends(cookie_auth)):
    request.state.api_token = bearer is not None
    token = bearer.credentials if bearer else (cookie or '')
    with db() as c:
        if bearer:
            row = c.execute('SELECT u.*,co.name AS company_name,t.scope AS api_scope FROM api_access_tokens t JOIN users u ON u.id=t.user_id JOIN companies co ON co.id=u.company_id WHERE t.token_hash=? AND t.expires>? AND u.active=1 AND u.deleted_at IS NULL', (digest(token),datetime.now(timezone.utc).timestamp())).fetchone()
        else:
            row = c.execute('SELECT u.*,co.name AS company_name FROM sessions s JOIN users u ON u.id=s.user_id JOIN companies co ON co.id=u.company_id WHERE s.token=? AND s.expires>? AND u.active=1 AND u.deleted_at IS NULL', (digest(token),datetime.now(timezone.utc).timestamp())).fetchone()
        mode = None
        if row and not bearer:
            row, mode = impersonation.resolve(c, request, row, digest(token), digest)
    if not row:
        raise HTTPException(401, 'Zaloguj się, aby kontynuować.')
    if row['must_change_password'] and not mode and request.url.path not in ('/api/me', '/api/me/password'):
        raise HTTPException(403, 'Zmień hasło tymczasowe, aby kontynuować.')
    if bearer and row['api_scope'] == 'read' and request.method not in ('GET', 'HEAD', 'OPTIONS'):
        raise HTTPException(403, 'Ten klucz API pozwala wyłącznie na odczyt.')
    result = admin.public_account(row)
    result.pop('api_scope', None)
    if mode:
        result['impersonation'] = mode
        result['must_change_password'] = False
        if mode.get('read_only'):
            result.update(can_read=True, can_edit=False, can_add=False, can_delete=False)
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                raise HTTPException(403, 'To podgląd konta tylko do odczytu. Wróć na konto administratora, aby wprowadzać zmiany.')
        if request.url.path == '/api/me/password' or request.url.path.startswith(('/api/access-tokens', '/api/admin/')):
            raise HTTPException(403, 'W trybie klienta nie można zmieniać haseł, kluczy API ani zarządzać administracją. Wróć na własne konto.')
    expected = request.headers.get('x-account-id')
    if expected and expected != result['id'] and request.url.path != impersonation.STOP_PATH:
        raise HTTPException(409, 'Konto w przeglądarce zostało zmienione. Odśwież tę kartę przed dalszą pracą.')
    return result

admin.install(app, db, user, password_hash)
companies.install(app, db, user)
api_tokens.install(app, db, user)
impersonation.install(app, db, user, digest, SECURE_COOKIE)
message_center.install(app, db, user)

class Credentials(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=10, max_length=200)

def session(response, user_id):
    token = secrets.token_urlsafe(32)
    with db() as c:
        c.execute('DELETE FROM sessions WHERE expires<?',(datetime.now(timezone.utc).timestamp(),))
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(digest(token),user_id,datetime.now(timezone.utc).timestamp()+604800))
    response.set_cookie('session',token,httponly=True,secure=SECURE_COOKIE,samesite='lax',max_age=604800)
    response.delete_cookie(impersonation.COOKIE)

@app.get('/api/setup')
def setup_status():
    with db() as c:
        return {'required': c.execute('SELECT count(*) FROM users').fetchone()[0] == 0}

@app.get('/api/health', tags=['System'])
def health():
    try:
        with db() as c:
            c.execute('SELECT 1').fetchone()
    except (database.psycopg.Error, OSError):
        raise HTTPException(503, 'Baza danych jest niedostępna.') from None
    return {'status': 'ok'}

@app.post('/api/setup',status_code=201)
def setup(body: Credentials, response: Response):
    if not body.name.strip():
        raise HTTPException(422,'Podaj nazwę użytkownika.')
    with db() as c:
        c.begin_write()
        if c.execute('SELECT count(*) FROM users').fetchone()[0]:
            raise HTTPException(409,'Konto administratora już istnieje.')
        uid = secrets.token_hex(16)
        c.execute("INSERT INTO users(id,name,password,role) VALUES(?,?,?,'admin')",(uid,body.name.strip(),password_hash(body.password)))
        companies.bind_superadmin(c)
        result = admin.public_account(c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())
    session(response,uid)
    return result

@app.post('/api/login')
def login(body: Credentials, response: Response, request: Request):
    with db() as c:
        row = c.execute('SELECT u.*,co.name AS company_name FROM users u JOIN companies co ON co.id=u.company_id WHERE u.name=?',(body.name.strip(),)).fetchone()
    stored = row['password'] if row else password_hash('dummy-password')
    if not hmac.compare_digest(password_hash(body.password,stored.split(':')[0]),stored) or not row or not row['active']:
        raise HTTPException(401,'Nieprawidłowa nazwa użytkownika lub hasło.')
    # Replacing an existing browser login must also detach its old push account.
    with db() as c:
        c.execute('DELETE FROM push_subscriptions WHERE session_token=?',
                  (digest(request.cookies.get('session', '')),))
    session(response,row['id'])
    return admin.public_account(row)

@app.post('/api/logout',status_code=204)
def logout(request: Request, response: Response):
    with db() as c:
        c.execute('DELETE FROM sessions WHERE token=?',(digest(request.cookies.get('session','')),))
    response.delete_cookie('session')
    response.delete_cookie(impersonation.COOKIE)

@app.get('/api/me')
def me(request: Request, response: Response, current=Depends(user)):
    if getattr(request.state, 'impersonation_expired', False):
        response.delete_cookie(impersonation.COOKIE)
    return current

class MenuOrderInput(BaseModel):
    menu_order: list[Literal['start', 'ai', 'mail', 'edelivery', 'tasks', 'calendar', 'notes', 'documents',
                             'surveys', 'drive', 'templates', 'dictionaries', 'companies', 'help', 'admin', 'planning', 'settings']] = Field(max_length=17)

    @field_validator('menu_order')
    @classmethod
    def unique_items(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('Pozycje menu nie mogą się powtarzać.')
        return value

@app.put('/api/me/menu-order')
def save_menu_order(body: MenuOrderInput, current=Depends(user)):
    with db() as c:
        c.begin_write()
        c.execute('UPDATE users SET menu_order=? WHERE id=?',
                  (json.dumps(body.menu_order), current['id']))
    return {'menu_order': body.menu_order}

class PasswordChange(BaseModel):
    current_password: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)

@app.post('/api/me/password')
def change_password(body: PasswordChange, request: Request, response: Response, current=Depends(user)):
    with db() as c:
        c.begin_write()
        row = c.execute('SELECT * FROM users WHERE id=?', (current['id'],)).fetchone()
        # Recheck the session inside the transaction in case a reset revoked it.
        if not row or not row['active'] or not c.execute('SELECT 1 FROM sessions WHERE token=? AND user_id=? AND expires>?',
                (digest(request.cookies.get('session', '')), current['id'], datetime.now(timezone.utc).timestamp())).fetchone():
            raise HTTPException(401, 'Zaloguj się, aby kontynuować.')
        stored = row['password']
        if not hmac.compare_digest(password_hash(body.current_password, stored.split(':')[0]), stored):
            raise HTTPException(422, 'Obecne hasło jest nieprawidłowe.')
        if body.new_password == body.current_password:
            raise HTTPException(422, 'Nowe hasło musi różnić się od obecnego.')
        c.execute('UPDATE users SET password=?,must_change_password=0 WHERE id=?', (password_hash(body.new_password), current['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?', (current['id'],))
        c.execute('DELETE FROM api_access_tokens WHERE user_id=?', (current['id'],))
        c.execute('DELETE FROM impersonation_sessions WHERE target_id=?', (current['id'],))
        result = admin.public_account(c.execute('SELECT * FROM users WHERE id=?', (current['id'],)).fetchone())
    session(response, current['id'])
    return result

class DocumentInput(BaseModel):
    title: str = Field(min_length=1,max_length=200)
    category: str = Field(default='Inne',max_length=60)
    content: str = Field(default='',max_length=500000)
    rich_content: dict | None = None
    field_source: dict | None = None
    field_values: dict[str, str] = Field(default_factory=dict)
    status: workflow.DocumentStatus = 'Szkic'
    version: int | None = None
    folder_id: str | None = None

def owned(c, doc_id, current, action='read'):
    row=c.execute('SELECT * FROM documents WHERE id=?',(doc_id,)).fetchone()
    if not row or not access.document_permissions(c, current, row)['read']:
        raise HTTPException(404,'Nie znaleziono dokumentu.')
    access.require(access.document_permissions(c, current, row), action)
    return row

def owned_folder(c, folder_id, current, action='read'):
    if folder_id is None:
        access.require(access.permissions(c,current,None), action)
        return
    row = c.execute('SELECT * FROM folders WHERE id=?', (folder_id,)).fetchone()
    if not row or not access.permissions(c,current,folder_id,row['user_id'])['read']:
        raise HTTPException(404, 'Nie znaleziono folderu.')
    access.require(access.permissions(c,current,folder_id,row['user_id']), action)
    return row

@app.get('/api/access')
def root_access(current=Depends(user)):
    with db() as c:
        return access.permissions(c,current,None)

class FolderInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = None
    access_mode: Literal['inherit', 'private', 'groups', 'users'] = 'inherit'
    group_ids: list[str] = Field(default_factory=list, max_length=100)
    user_ids: list[str] = Field(default_factory=list, max_length=100)
    can_add: bool = False
    can_delete: bool = False
    can_edit: bool = False

@app.get('/api/sharing-options')
def sharing_options(current=Depends(user)):
    with db() as c:
        return {
            'users': [dict(row) for row in c.execute('SELECT id,name FROM users WHERE active=1 AND id!=? ORDER BY name', (current['id'],))],
            'groups': [dict(row) for row in c.execute('SELECT id,name FROM groups ORDER BY name')]
        }

@app.get('/api/folders')
def folders(current=Depends(user)):
    with db() as c:
        all_folders = {row['id']: dict(row) for row in c.execute('SELECT * FROM folders ORDER BY lower(name)')}
        visible = set()
        for folder in all_folders.values():
            folder['permissions'] = access.permissions(c,current,folder['id'],folder['user_id'])
            folder['can_share'] = external_shares.can_manage(c, current, folder, 'folder')
            if folder['permissions']['read']:
                ancestor = folder
                while ancestor and ancestor['id'] not in visible:
                    visible.add(ancestor['id'])
                    ancestor = all_folders.get(ancestor['parent_id'])
        for row in c.execute('SELECT user_id,folder_id,filename,uploaded_by FROM documents WHERE folder_id IS NOT NULL'):
            if access.document_permissions(c,current,row)['read']:
                ancestor = all_folders.get(row['folder_id'])
                while ancestor and ancestor['id'] not in visible:
                    visible.add(ancestor['id'])
                    ancestor = all_folders.get(ancestor['parent_id'])
        return [folder for folder in all_folders.values() if folder['id'] in visible]

class FolderRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)

@app.patch('/api/folders/{folder_id}')
def rename_folder(folder_id: str, body: FolderRename, current=Depends(user)):
    name = body.name.strip()
    if not name or name in ('.', '..') or any(character in name for character in ('/', '\\', '\x00')):
        raise HTTPException(422, 'Podaj nazwę folderu bez ukośników.')
    try:
        with db() as c:
            c.begin_write()
            previous = owned_folder(c,folder_id,current,'edit')
            c.execute('UPDATE folders SET name=? WHERE id=?', (name,folder_id))
            audit.updated(c, current, 'folder', previous, ['name'])
            return dict(c.execute('SELECT * FROM folders WHERE id=?', (folder_id,)).fetchone())
    except database.IntegrityError:
        raise HTTPException(409, 'Folder o tej nazwie już istnieje w tym miejscu.') from None

@app.post('/api/folders', status_code=201)
def create_folder(body: FolderInput, current=Depends(user)):
    name = body.name.strip()
    if not name or name in ('.', '..') or any(character in name for character in ('/', '\\', '\x00')):
        raise HTTPException(422, 'Podaj nazwę folderu bez ukośników.')
    folder_id = secrets.token_hex(16)
    try:
        with db() as c:
            c.begin_write()
            owned_folder(c, body.parent_id, current, 'add')
            parent_rights = access.permissions(c,current,body.parent_id)
            if body.access_mode == 'groups' and (not body.group_ids or body.user_ids):
                raise HTTPException(422, 'Wybierz co najmniej jedną grupę.')
            if body.access_mode == 'users' and (not body.user_ids or body.group_ids):
                raise HTTPException(422, 'Wybierz co najmniej jednego użytkownika.')
            if body.access_mode in ('private', 'inherit') and (body.group_ids or body.user_ids):
                raise HTTPException(422, 'Dla tego trybu nie wybieraj grup ani użytkowników.')
            if body.access_mode in ('groups', 'users'):
                for action in ('add', 'edit', 'delete'):
                    if getattr(body,'can_' + action) and current['role'] != 'admin':
                        access.require(parent_rights, action)
            for group_id in set(body.group_ids):
                if not c.execute('SELECT 1 FROM groups WHERE id=?', (group_id,)).fetchone():
                    raise HTTPException(422, 'Wybrana grupa nie istnieje.')
            for user_id in set(body.user_ids):
                if user_id == current['id'] or not c.execute('SELECT 1 FROM users WHERE id=? AND active=1', (user_id,)).fetchone():
                    raise HTTPException(422, 'Wybierz innego aktywnego użytkownika.')
            c.execute('INSERT INTO folders(id,user_id,name,parent_id,created_at,access_mode) VALUES(?,?,?,?,?,?)',
                      (folder_id,current['id'],name,body.parent_id,now(),body.access_mode))
            if body.access_mode != 'inherit':
                # Keep the creator's existing rights when the folder stops inheriting access.
                c.execute('INSERT INTO folder_user_permissions VALUES(?,?,?,?,?,?)',
                          (folder_id,current['id'],True,parent_rights['edit'],parent_rights['add'],parent_rights['delete']))
            for group_id in set(body.group_ids):
                c.execute('INSERT INTO group_permissions VALUES(?,?,?,?,?,?,?)',
                          (group_id,folder_id,folder_id,True,body.can_edit,body.can_add,body.can_delete))
            for user_id in set(body.user_ids):
                c.execute('INSERT INTO folder_user_permissions VALUES(?,?,?,?,?,?)',
                          (folder_id,user_id,True,body.can_edit,body.can_add,body.can_delete))
            result = dict(owned_folder(c, folder_id, current))
            audit.record(c, current, 'folder', result, 'Utworzono', [audit.change('access_mode', None, body.access_mode), audit.change('permissions', None, body.model_dump(exclude={'name', 'parent_id'}))])
    except database.IntegrityError:
        raise HTTPException(409, 'Folder o tej nazwie już istnieje w tym miejscu.') from None
    return result

@app.delete('/api/folders/{folder_id}', status_code=204)
def delete_folder(folder_id: str, current=Depends(user)):
    with db() as c:
        c.begin_write()
        previous = owned_folder(c, folder_id, current, 'delete')
        has_files = c.execute('SELECT 1 FROM documents WHERE folder_id=? LIMIT 1', (folder_id,)).fetchone()
        has_folders = c.execute('SELECT 1 FROM folders WHERE parent_id=? LIMIT 1', (folder_id,)).fetchone()
        if has_files or has_folders:
            raise HTTPException(409, 'Folder nie jest pusty. Najpierw usuń jego pliki i podfoldery.')
        audit.record(c, current, 'folder', previous, 'Usunięto')
        c.execute('DELETE FROM folders WHERE id=?', (folder_id,))

def document(row):
    result = document_fields.decode(row)
    result['has_file'] = result.pop('file',None) is not None or bool(result.get('object_key'))
    result.pop('object_key', None)
    result.pop('object_bucket', None)
    return result

@app.get('/api/documents')
def documents(current=Depends(user)):
    with db() as c:
        rows=c.execute('SELECT id,user_id,uploaded_by,folder_id,title,category,status,created_at,updated_at,version,filename,coalesce(file_size,length(file)) AS file_size FROM documents ORDER BY updated_at DESC').fetchall()
        result=[]
        for row in rows:
            item=dict(row)
            item['permissions'] = access.document_permissions(c,current,row)
            item['can_share'] = external_shares.can_manage(c, current, row, 'document')
            if not item['permissions']['read']:
                continue
            item['comment_count']=c.execute('SELECT count(*) FROM comments WHERE document_id=?',(row['id'],)).fetchone()[0]
            item['deadlines']=[dict(r) for r in c.execute('SELECT * FROM deadlines WHERE document_id=? ORDER BY due_at',(row['id'],))]
            pending_approvals = 0
            if row['filename'] and row['user_id'] == current['id'] and (row['uploaded_by'] or row['user_id']) == current['id']:
                item['approvals'] = mailing.summary(c, row['id'], current['id'], row['version'])
                pending_approvals = mailing.summary(c, row['id'], current['id'], None)['waiting']
            item['active_actions'] = workflow.active_actions(row['status'], pending_approvals, item['deadlines'])
            result.append(item)
        return result

@app.post('/api/documents',status_code=201)
def create_document(body: DocumentInput, current=Depends(user)):
    if not body.title.strip():
        raise HTTPException(422,'Podaj tytuł dokumentu.')
    doc_id=secrets.token_hex(16)
    with db() as c:
        c.begin_write()
        owned_folder(c,body.folder_id,current,'add')
        content, formatted, field_source, field_values = document_fields.prepare(body.content, body.rich_content, body.field_source, body.field_values)
        c.execute('INSERT INTO documents(id,user_id,title,category,content,status,created_at,updated_at,folder_id,rich_content,field_source,field_values) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(doc_id,current['id'],body.title.strip(),body.category,content,body.status,now(),now(),body.folder_id,formatted,field_source,field_values))
        audit.record(c, current, 'document', c.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone(), 'Utworzono dokument')
    return get_document(doc_id,current)

@app.post('/api/files',status_code=201)
async def upload_file(file: UploadFile=File(...),folder_id: str | None=Form(None),current=Depends(user)):
    with db() as c:
        owned_folder(c, folder_id, current, 'add')
    data=await file.read(MAX_UPLOAD+1)
    await file.close()
    if len(data)>MAX_UPLOAD:
        raise HTTPException(413,'Maksymalny rozmiar pliku to 10 MB.')
    filename=Path((file.filename or 'plik').replace('\\','/')).name or 'plik'
    doc_id=secrets.token_hex(16)
    timestamp=now()
    bucket, key = await run_in_threadpool(storage.put, data, current['id'])
    try:
        with db() as c:
            c.begin_write()
            owned_folder(c, folder_id, current, 'add')
            c.execute('INSERT INTO documents(id,user_id,title,category,content,status,created_at,updated_at,filename,file,object_bucket,object_key,file_size,folder_id,uploaded_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (doc_id,current['id'],filename[:200],'Pliki','','Gotowy',timestamp,timestamp,filename,None if key else data,bucket,key,len(data),folder_id,current['id']))
            audit.record(c, current, 'document', c.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone(), 'Dodano plik', [audit.change('filename', None, filename), audit.change('file_size', None, len(data))])
    except Exception:
        await run_in_threadpool(storage.cleanup, bucket, key)
        raise
    return get_document(doc_id,current)

@app.get('/api/documents/{doc_id}')
def get_document(doc_id: str, current=Depends(user)):
    with db() as c:
        row = owned(c,doc_id,current)
        result=document(row)
        result['permissions'] = access.document_permissions(c,current,row)
        result['can_share'] = external_shares.can_manage(c, current, row, 'document')
        result['comments']=[dict(r) for r in c.execute('SELECT * FROM comments WHERE document_id=? ORDER BY created_at',(doc_id,))]
        result['deadlines']=[dict(r) for r in c.execute('SELECT * FROM deadlines WHERE document_id=? ORDER BY due_at',(doc_id,))]
        result['shares']=[dict(r) for r in c.execute('SELECT id,expires,revoked,created_at FROM shares WHERE document_id=? ORDER BY created_at DESC',(doc_id,))]
        return result

@app.put('/api/documents/{doc_id}')
def update_document(doc_id: str, body: DocumentInput, current=Depends(user)):
    if not body.title.strip():
        raise HTTPException(422,'Podaj tytuł dokumentu.')
    with db() as c:
        c.begin_write()
        row=owned(c,doc_id,current,'edit')
        if body.version != row['version']:
            raise HTTPException(409,'Dokument zmienił się w innym oknie. Otwórz go ponownie przed zapisem.')
        content, formatted, field_source, field_values = document_fields.prepare(body.content, body.rich_content, body.field_source, body.field_values)
        c.execute('UPDATE documents SET title=?,category=?,content=?,rich_content=?,field_source=?,field_values=?,status=?,updated_at=?,version=version+1 WHERE id=?',(body.title.strip(),body.category,content,formatted,field_source,field_values,body.status,now(),doc_id))
        audit.updated(c, current, 'document', row, ['title', 'category', 'content', 'rich_content', 'field_source', 'field_values', 'status'])
    return get_document(doc_id,current)

class WorkflowInput(BaseModel):
    status: workflow.DocumentStatus
    version: int = Field(strict=True, ge=1)

class DocumentMoveInput(BaseModel):
    folder_id: str | None
    version: int = Field(strict=True, ge=1)

@app.patch('/api/documents/{doc_id}/move')
def move_document(doc_id: str, body: DocumentMoveInput, current=Depends(user)):
    with db() as c:
        c.begin_write()
        row = owned(c, doc_id, current)
        if not access.document_permissions(c, current, row)['move']:
            raise HTTPException(403, 'Brak uprawnienia do przenoszenia tego pliku.')
        owned_folder(c, body.folder_id, current, 'add')
        if body.version != row['version']:
            raise HTTPException(409, 'Dokument został zmieniony. Odśwież listę i spróbuj ponownie.')
        if row['folder_id'] != body.folder_id:
            # Moving changes location only; file versions and their approvals remain valid.
            c.execute('UPDATE documents SET folder_id=?,updated_at=? WHERE id=?', (body.folder_id, now(), doc_id))
            audit.updated(c, current, 'document', row, ['folder_id'], action='Przeniesiono dokument')
            for folder_id, action in ((row['folder_id'], 'Przeniesiono z katalogu: '), (body.folder_id, 'Przeniesiono do katalogu: ')):
                if folder_id:
                    folder = c.execute('SELECT * FROM folders WHERE id=?', (folder_id,)).fetchone()
                    audit.record(c, current, 'folder', folder, action + row['title'], [audit.change('document_id', None, doc_id)])
    return get_document(doc_id, current)

@app.get('/api/documents/{doc_id}/pdf')
def download_document_pdf(doc_id: str, current=Depends(user)):
    from backend.document_pdf import render_pdf
    from urllib.parse import quote
    with db() as c:
        row = owned(c, doc_id, current)
        if row['filename']:
            if Path(row['filename']).suffix.lower() != '.pdf':
                raise HTTPException(415, 'Eksport PDF jest dostępny dla dokumentów utworzonych w edytorze.')
            return file_response(row)
        result = document(row)
    filename = result['title'].replace('/', '_').replace('\\', '_') + '.pdf'
    return Response(render_pdf(result), media_type='application/pdf', headers={
        'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename, safe=''), 'Cache-Control': 'no-store'})

@app.patch('/api/documents/{doc_id}/status')
def change_document_status(doc_id: str, body: WorkflowInput, current=Depends(user)):
    with db() as c:
        c.begin_write()
        row = owned(c, doc_id, current, 'workflow')
        if row['version'] != body.version:
            raise HTTPException(409, 'Dokument został zmieniony. Odśwież listę i spróbuj ponownie.')
        if row['status'] != body.status:
            c.execute('UPDATE documents SET status=?,updated_at=?,version=version+1 WHERE id=?', (body.status, now(), doc_id))
            audit.updated(c, current, 'document', row, ['status'])
    return get_document(doc_id, current)

@app.delete('/api/documents/{doc_id}',status_code=204)
def delete_document(doc_id: str,current=Depends(user)):
    with db() as c:
        c.begin_write()
        row = owned(c,doc_id,current,'delete')
        copies = c.execute('SELECT object_bucket,object_key FROM file_mailings WHERE document_id=?', (doc_id,)).fetchall()
        bucket, key = row['object_bucket'], row['object_key']
        storage.delete(bucket, key)
        audit.record(c, current, 'document', row, 'Usunięto')
        if row['folder_id'] is not None:
            folder = c.execute('SELECT * FROM folders WHERE id=?', (row['folder_id'],)).fetchone()
            audit.record(c, current, 'folder', folder,
                ('Usunięto plik: ' if row['filename'] else 'Usunięto dokument: ') + (row['filename'] or row['title']),
                [audit.change('title', row['title'], None), audit.change('filename', row['filename'], None),
                 audit.change('document_id', row['id'], None)])
        c.execute('DELETE FROM documents WHERE id=?',(doc_id,))
    for copy in copies:
        storage.cleanup(copy['object_bucket'], copy['object_key'])

@app.post('/api/documents/{doc_id}/file')
async def attach_file(doc_id: str,file: UploadFile=File(...),current=Depends(user)):
    data=await file.read(MAX_UPLOAD+1)
    await file.close()
    if len(data)>MAX_UPLOAD:
        raise HTTPException(413,'Maksymalny rozmiar pliku to 10 MB.')
    filename=Path((file.filename or 'plik').replace('\\','/')).name or 'plik'
    with db() as c:
        previous = owned(c,doc_id,current,'edit')
        if previous['filename'] and (previous['uploaded_by'] or previous['user_id']) != current['id']:
            raise HTTPException(403, 'Załącznik może zastąpić tylko osoba, która go dodała.')
    bucket, key = await run_in_threadpool(storage.put, data, current['id'])
    try:
        with db() as c:
            c.begin_write()
            previous = owned(c,doc_id,current,'edit')
            if previous['filename'] and (previous['uploaded_by'] or previous['user_id']) != current['id']:
                raise HTTPException(403, 'Załącznik może zastąpić tylko osoba, która go dodała.')
            previous_bucket, previous_key = previous['object_bucket'], previous['object_key']
            c.execute('UPDATE documents SET filename=?,file=?,object_bucket=?,object_key=?,file_size=?,uploaded_by=?,updated_at=?,version=version+1 WHERE id=?',
                      (filename,None if key else data,bucket,key,len(data),current['id'],now(),doc_id))
            audit.record(c, current, 'document', previous, 'Zastąpiono plik' if previous['filename'] else 'Dodano plik', [audit.change('filename', previous['filename'], filename), audit.change('file_size', previous['file_size'], len(data))])
    except Exception:
        await run_in_threadpool(storage.cleanup, bucket, key)
        raise
    await run_in_threadpool(storage.cleanup, previous_bucket, previous_key)
    return get_document(doc_id,current)

def file_response(row, preview=False):
    if row['file'] is None and not row['object_key']:
        raise HTTPException(404,'Dokument nie ma załącznika.')
    from urllib.parse import quote
    headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['filename']), 'Cache-Control':'no-store'}
    media_type = 'application/octet-stream'
    if preview:
        media_type = {
            '.pdf': 'application/pdf',
            '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
            '.svg': 'image/svg+xml', '.avif': 'image/avif', '.ico': 'image/vnd.microsoft.icon'
        }.get(Path(row['filename']).suffix.lower())
        if not media_type:
            raise HTTPException(415, 'Ten format nie obsługuje podglądu w przeglądarce.')
        headers['Content-Disposition'] = "inline; filename*=UTF-8''"+quote(row['filename'])
        headers['Content-Security-Policy'] = "sandbox; default-src 'none'; style-src 'unsafe-inline'"
    if row['object_key']:
        body = storage.get(row['object_bucket'], row['object_key'])
        def chunks():
            try:
                yield from body.iter_chunks(chunk_size=64 * 1024)
            finally:
                body.close()
        return StreamingResponse(chunks(),media_type=media_type,headers=headers)
    return Response(row['file'],media_type=media_type,headers=headers)

@app.get('/api/documents/{doc_id}/file')
def download_file(doc_id: str,current=Depends(user)):
    with db() as c:
        return file_response(owned(c,doc_id,current))

@app.get('/api/folders/{folder_id}/archive')
def download_folder_archive(folder_id: str, current=Depends(user)):
    from urllib.parse import quote
    from starlette.background import BackgroundTask
    with db() as c:
        folder = owned_folder(c, folder_id, current)
        output = folder_archive.build(c, folder, current, document)
    return StreamingResponse(folder_archive.chunks(output), media_type='application/zip', headers={
        'Content-Disposition': "attachment; filename*=UTF-8''" + quote(folder_archive.safe_name(folder['name']) + '.zip', safe=''),
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'}, background=BackgroundTask(output.close))

@app.get('/api/documents/{doc_id}/preview')
def preview_file(doc_id: str,current=Depends(user)):
    with db() as c:
        return file_response(owned(c,doc_id,current), preview=True)

def image_bytes(row):
    if row['object_key']:
        body = storage.get(row['object_bucket'], row['object_key'])
        try:
            data = body.read(MAX_UPLOAD + 1)
        finally:
            body.close()
    else:
        data = row['file']
    if data is None:
        raise HTTPException(404, 'Dokument nie ma załącznika.')
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, 'Maksymalny rozmiar pliku to 10 MB.')
    return data

def can_edit_image(c, current, row):
    return (row['user_id'] == current['id'] and
            (row['uploaded_by'] or row['user_id']) == current['id'] and
            access.permissions(c, current, row['folder_id'], row['user_id'])['edit'])

@app.get('/api/documents/{doc_id}/image')
def image_info(doc_id: str, current=Depends(user)):
    with db() as c:
        row = owned(c, doc_id, current)
        allowed = can_edit_image(c, current, row)
    tags = [{'name': 'Nazwa pliku', 'value': row['filename']},
            {'name': 'Rozmiar pliku (bajty)', 'value': str(row['file_size'] or len(row['file'] or b''))},
            {'name': 'Dodano', 'value': row['created_at']}, {'name': 'Zmieniono', 'value': row['updated_at']}]
    try:
        info = images.metadata(image_bytes(row))
    except (OSError, ValueError, SyntaxError):
        info = {'width': 0, 'height': 0, 'supported': False, 'tags': [], 'reason': 'Nie można odczytać danych tego obrazu.'}
    except HTTPException as exc:
        if exc.status_code != 415:
            raise
        info = {'width': 0, 'height': 0, 'supported': False, 'tags': [], 'reason': exc.detail}
    info['tags'] = tags + info['tags']
    info['can_edit'] = allowed and info['supported']
    info['version'] = row['version']
    return info

@app.post('/api/documents/{doc_id}/image')
def edit_image(doc_id: str, body: images.ImageEdit, current=Depends(user)):
    def check(c):
        row = owned(c, doc_id, current)
        if not can_edit_image(c, current, row):
            raise HTTPException(403, 'Obraz może edytować tylko jego autor z uprawnieniem do edycji.')
        if row['version'] != body.version:
            raise HTTPException(409, 'Plik został zmieniony. Otwórz edytor ponownie.')
        return row
    with db() as c:
        row = check(c)
    try:
        data = images.transform(image_bytes(row), body)
    except (OSError, ValueError, SyntaxError) as exc:
        raise HTTPException(415, 'Nie można przetworzyć tego obrazu.') from exc
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, 'Wynik przekracza maksymalny rozmiar 10 MB.')
    bucket, key = storage.put(data, current['id'])
    try:
        with db() as c:
            c.begin_write()
            previous = check(c)
            c.execute('UPDATE documents SET file=?,object_bucket=?,object_key=?,file_size=?,updated_at=?,version=version+1 WHERE id=?',
                      (None if key else data, bucket, key, len(data), now(), doc_id))
            audit.record(c, current, 'document', previous, 'Edytowano obraz', [audit.change('crop', None, body.model_dump(exclude={'version'})), audit.change('file_size', previous['file_size'], len(data))])
    except Exception:
        storage.cleanup(bucket, key)
        raise
    storage.cleanup(previous['object_bucket'], previous['object_key'])
    return get_document(doc_id, current)

class CommentInput(BaseModel):
    content: str = Field(min_length=1,max_length=5000)

@app.post('/api/documents/{doc_id}/comments',status_code=201)
def add_comment(doc_id: str,body: CommentInput,current=Depends(user)):
    if not body.content.strip():
        raise HTTPException(422,'Komentarz nie może być pusty.')
    with db() as c:
        row = owned(c,doc_id,current,'edit')
        c.execute('INSERT INTO comments VALUES(?,?,?,?,?)',(secrets.token_hex(16),doc_id,current['name'],body.content.strip(),now()))
        audit.record(c, current, 'document', row, 'Dodano komentarz', [audit.change('comment', None, body.content.strip())])
    return get_document(doc_id,current)

class DeadlineInput(BaseModel):
    title: str = Field(min_length=1,max_length=200)
    due_at: datetime

@app.post('/api/documents/{doc_id}/deadlines',status_code=201)
def add_deadline(doc_id: str,body: DeadlineInput,current=Depends(user)):
    if not body.title.strip() or body.due_at.tzinfo is None:
        raise HTTPException(422,'Podaj nazwę i termin ze strefą czasową.')
    with db() as c:
        row = owned(c,doc_id,current,'edit')
        c.execute('INSERT INTO deadlines VALUES(?,?,?,?,0)',(secrets.token_hex(16),doc_id,body.title.strip(),body.due_at.astimezone(timezone.utc).isoformat()))
        audit.record(c, current, 'document', row, 'Dodano termin', [audit.change('deadline', None, {'title': body.title.strip(), 'due_at': body.due_at.isoformat()})])
    return get_document(doc_id,current)

class DoneInput(BaseModel):
    done: bool

@app.patch('/api/documents/{doc_id}/deadlines/{deadline_id}')
def finish_deadline(doc_id: str,deadline_id: str,body: DoneInput,current=Depends(user)):
    with db() as c:
        c.begin_write()
        row = owned(c,doc_id,current,'edit')
        previous = c.execute('SELECT * FROM deadlines WHERE id=? AND document_id=?', (deadline_id, doc_id)).fetchone()
        if c.execute('UPDATE deadlines SET done=? WHERE id=? AND document_id=?',(body.done,deadline_id,doc_id)).rowcount==0:
            raise HTTPException(404,'Nie znaleziono terminu.')
        if bool(previous['done']) != body.done: audit.record(c, current, 'document', row, 'Zmieniono termin', [audit.change('deadline', None, previous['title']), audit.change('done', bool(previous['done']), body.done)])
    return get_document(doc_id,current)

class ShareInput(BaseModel):
    hours: int = Field(default=24,ge=1,le=720)

@app.post('/api/documents/{doc_id}/shares',status_code=201)
def create_share(doc_id: str,body: ShareInput,current=Depends(user)):
    token=secrets.token_urlsafe(32)
    expires=datetime.now(timezone.utc).timestamp()+body.hours*3600
    with db() as c:
        row = owned(c,doc_id,current,'edit')
        c.execute('INSERT INTO shares VALUES(?,?,?,?,0,?)',(secrets.token_hex(16),digest(token),doc_id,expires,now()))
        audit.record(c, current, 'document', row, 'Utworzono link udostępnienia', [audit.change('expires', None, datetime.fromtimestamp(expires, timezone.utc).isoformat())])
    return {'path':'/share/'+token,'expires':expires}

@app.delete('/api/documents/{doc_id}/shares/{share_id}',status_code=204)
def revoke_share(doc_id: str,share_id: str,current=Depends(user)):
    with db() as c:
        c.begin_write()
        row = owned(c,doc_id,current,'edit')
        previous = c.execute('SELECT revoked FROM shares WHERE id=? AND document_id=?', (share_id, doc_id)).fetchone()
        if c.execute('UPDATE shares SET revoked=1 WHERE id=? AND document_id=?',(share_id,doc_id)).rowcount==0:
            raise HTTPException(404,'Nie znaleziono linku.')
        if not previous['revoked']: audit.record(c, current, 'document', row, 'Wyłączono link udostępnienia')

def shared_row(c,token):
    share=c.execute('SELECT * FROM shares WHERE token_hash=?',(digest(token),)).fetchone()
    if not share:
        raise HTTPException(404,'Link nie istnieje.')
    if share['revoked'] or share['expires']<=datetime.now(timezone.utc).timestamp():
        raise HTTPException(410,'Link wygasł lub został wyłączony.')
    return c.execute('SELECT * FROM documents WHERE id=?',(share['document_id'],)).fetchone(),share

@app.get('/api/shared/{token}')
def read_shared(token: str):
    with db() as c:
        row,share=shared_row(c,token)
        return {'title':row['title'],'content':row['content'],'rich_content':richtext.decode(row)['rich_content'],'category':row['category'],'filename':row['filename'],'expires':share['expires']}

@app.get('/api/shared/{token}/file')
def shared_file(token: str):
    with db() as c:
        row,_=shared_row(c,token)
        return file_response(row)

class TemplateInput(BaseModel):
    title: str=Field(min_length=1,max_length=200)
    category: str=Field(default='Inne',max_length=60)
    description: str=Field(default='',max_length=500)
    content: str=Field(max_length=500000)
    rich_content: dict | None = None
    version: int | None = Field(default=None, ge=1)

def template_details(row, c, current):
    result = richtext.decode(row)
    rights = access.permissions(c, current, None)
    can_edit = row['user_id'] == current['id'] or (row['user_id'] is None and current['role'] == 'admin')
    result['permissions'] = {'edit': can_edit and rights['edit'], 'delete': can_edit and rights['delete'], 'add': rights['add']}
    return result

@app.get('/api/templates')
def templates(current=Depends(user)):
    with db() as c:
        return [template_details(r,c,current) for r in c.execute('SELECT * FROM templates WHERE user_id IS NULL OR user_id=? ORDER BY user_id IS NULL,lower(title)',(current['id'],))]

@app.post('/api/templates',status_code=201)
def create_template(body: TemplateInput,current=Depends(user)):
    if not body.title.strip():
        raise HTTPException(422,'Podaj nazwę szablonu.')
    template_id=secrets.token_hex(16)
    with db() as c:
        access.require(access.permissions(c,current,None),'add')
        content, formatted = richtext.fields(body.content, body.rich_content)
        c.execute('INSERT INTO templates(id,user_id,title,category,description,content,rich_content) VALUES(?,?,?,?,?,?,?)',(template_id,current['id'],body.title.strip(),body.category,body.description,content,formatted))
        audit.record(c, current, 'template', c.execute('SELECT * FROM templates WHERE id=?', (template_id,)).fetchone(), 'Utworzono szablon')
        return template_details(c.execute('SELECT * FROM templates WHERE id=?', (template_id,)).fetchone(), c, current)

@app.put('/api/templates/{template_id}')
def update_template(template_id: str, body: TemplateInput, current=Depends(user)):
    if not body.title.strip():
        raise HTTPException(422, 'Podaj nazwę szablonu.')
    with db() as c:
        c.begin_write()
        row = c.execute('SELECT * FROM templates WHERE id=?', (template_id,)).fetchone()
        if not row or (row['user_id'] is not None and row['user_id'] != current['id']):
            raise HTTPException(404, 'Nie znaleziono szablonu.')
        if not template_details(row, c, current)['permissions']['edit']:
            raise HTTPException(403, 'Brak uprawnienia do edycji szablonu. Gotowe wzory może edytować administrator.')
        if body.version != row['version']:
            raise HTTPException(409, 'Szablon został zmieniony. Otwórz go ponownie przed zapisem.')
        content, formatted = richtext.fields(body.content, body.rich_content)
        c.execute('UPDATE templates SET title=?,category=?,description=?,content=?,rich_content=?,version=version+1 WHERE id=?',
                  (body.title.strip(),body.category,body.description,content,formatted,template_id))
        audit.updated(c, current, 'template', row, ['title', 'category', 'description', 'content', 'rich_content'])
        return template_details(c.execute('SELECT * FROM templates WHERE id=?', (template_id,)).fetchone(), c, current)

@app.delete('/api/templates/{template_id}', status_code=204)
def delete_template(template_id: str, current=Depends(user)):
    with db() as c:
        c.begin_write()
        row = c.execute('SELECT * FROM templates WHERE id=?', (template_id,)).fetchone()
        if not row or (row['user_id'] is not None and row['user_id'] != current['id']):
            raise HTTPException(404, 'Nie znaleziono szablonu.')
        access.require(template_details(row, c, current)['permissions'], 'delete')
        if row['user_id'] is None:
            c.execute('INSERT INTO deleted_default_templates(id) VALUES(?) ON CONFLICT DO NOTHING', (template_id,))
        audit.record(c, current, 'template', row, 'Usunięto')
        c.execute('DELETE FROM templates WHERE id=?', (template_id,))
    return Response(status_code=204)

ai_requests = ai.requests

@app.get('/api/ai/config')
def ai_configuration(current=Depends(user)):
    return ai.configuration()

@app.post('/api/ai/generate')
async def generate_with_ai(body: ai.GenerationInput, current=Depends(user)):
    if not body.prompt.strip():
        raise HTTPException(422, 'Opisz dokument, szablon lub ankietę, które chcesz wygenerować.')
    if body.kind in ('template', 'survey') and body.folder_id is not None:
        raise HTTPException(422, 'Szablony i ankiety nie są przypisywane do folderów.')
    if body.kind != 'survey':
        with db() as c:
            owned_folder(c, body.folder_id if body.kind == 'document' else None, current, 'add')
    if current['id'] in ai_requests:
        raise HTTPException(429, 'Poczekaj na zakończenie poprzedniego generowania.')
    ai_requests.add(current['id'])
    try:
        return await ai.generate(body)
    finally:
        ai_requests.discard(current['id'])

@app.post('/api/ai/templates/from-file')
async def template_from_file(file: UploadFile = File(...), prompt: str = Form('', max_length=8000), current=Depends(user)):
    try:
        with db() as c:
            access.require(access.permissions(c, current, None), 'add')
        if current['id'] in ai_requests:
            raise HTTPException(429, 'Poczekaj na zakończenie poprzedniego generowania.')
        ai_requests.add(current['id'])
        try:
            data = await file.read(ai_files.MAX_BYTES + 1)
            attachment = await run_in_threadpool(ai_files.attachment, file.filename, data)
            body = ai.GenerationInput(prompt=prompt.strip() or 'Utwórz szablon na podstawie załączonego dokumentu.', kind='template')
            return await ai.generate(body, attachment=attachment)
        finally:
            ai_requests.discard(current['id'])
    finally:
        await file.close()

saved_data.install(app, db, user, now)
dictionaries.install(app, db, user, now)
dictionary_excel.install(app, db, user, now)
ai_commands.install(app, db, user, now)
assistant.install(app, user)
notes.install(app, db, user, now)
flows.install(app, db, user, now)
edelivery_connection.install(app, db, user, now)
edelivery.install(app, db, user, now)
client_mail.install(app, db, user, now, owned_document=owned)
mail_daily.install(app, db, user, now)
mail_settings.install(app, db, user)
surveys.install(app, db, user, now)
audit.install(app, db, user)
tasks.install(app, db, user, owned, now)
mailing.install(app, db, user, owned, file_response, image_bytes, now, digest)
webpush.install(app, db, user)
external_shares.install(app, db, user, now, document, file_response, image_bytes)

# A built Vue frontend is served by Python from the same origin.
if (ROOT / 'dist' / 'assets').exists():
    app.mount('/assets', StaticFiles(directory=ROOT/'dist'/'assets'),name='assets')
if (ROOT / 'dist' / 'product').exists():
    app.mount('/product', StaticFiles(directory=ROOT/'dist'/'product'),name='product')

@app.get('/{path:path}',include_in_schema=False)
def frontend(path: str):
    if path.startswith('api/'):
        raise HTTPException(404,'Nie znaleziono endpointu.')
    if path in ('icon.svg','icon-192.png','icon-512.png','icon-maskable-512.png','manifest.webmanifest','sw.js','offline.html'):
        return FileResponse(ROOT/'dist'/path, headers={'Cache-Control': 'no-cache'})
    index=ROOT/'dist'/'index.html'
    if not index.exists():
        raise HTTPException(503,'Uruchom frontend przez npm run dev lub zbuduj go przez npm run build.')
    return FileResponse(index,headers={'Cache-Control':'no-store'})
