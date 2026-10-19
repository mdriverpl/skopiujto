"""Company directory and the single, explicitly designated superadministrator."""
import os
import secrets
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from backend import database

DEFAULT_COMPANY_ID = 'default-company'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS companies(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, nip TEXT NOT NULL DEFAULT '',
 address TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
 version INTEGER NOT NULL DEFAULT 1);
CREATE UNIQUE INDEX IF NOT EXISTS company_names ON companies(lower(name));
'''

class CompanyInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    nip: str = Field(default='', max_length=20)
    address: str = Field(default='', max_length=500)
    email: str = Field(default='', max_length=254)
    phone: str = Field(default='', max_length=50)
    version: int | None = Field(default=None, ge=1)

    @field_validator('name', 'nip', 'address', 'email', 'phone')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if any(ord(char) < 32 for char in value):
            raise ValueError('Usuń znaki sterujące z danych firmy.')
        return value

    @field_validator('name')
    @classmethod
    def required_name(cls, value):
        if not value:
            raise ValueError('Podaj nazwę firmy.')
        return value


def bind_superadmin(con):
    # Once bound, authority follows the immutable account ID, never a changed email.
    if con.execute('SELECT id FROM users WHERE is_superadmin=1').fetchone():
        return
    selector = os.getenv('EDOCUMENTS_SUPERADMIN_ACCOUNT', '').strip()
    if not selector:
        return
    matches = list(con.execute('SELECT id FROM users WHERE lower(name)=lower(?) OR lower(email)=lower(?)', (selector, selector)))
    if len(matches) > 1:
        raise RuntimeError('EDOCUMENTS_SUPERADMIN_ACCOUNT wskazuje więcej niż jedno konto. Ustaw unikalną nazwę użytkownika.')
    if matches:
        con.execute("UPDATE users SET is_superadmin=1,role='admin' WHERE id=?", (matches[0]['id'],))


def initialize(con):
    con.executescript(SCHEMA)
    con.execute('INSERT INTO companies(id,name) VALUES(?,?) ON CONFLICT(id) DO NOTHING', (DEFAULT_COMPANY_ID, 'Firma domyślna'))
    if 'company_id' not in con.columns('users'):
        con.execute("ALTER TABLE users ADD COLUMN company_id TEXT NOT NULL DEFAULT 'default-company' REFERENCES companies(id) ON DELETE RESTRICT")
    if 'is_superadmin' not in con.columns('users'):
        con.execute('ALTER TABLE users ADD COLUMN is_superadmin INTEGER NOT NULL DEFAULT 0 CHECK (is_superadmin IN (0,1))')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS single_superadmin ON users(is_superadmin) WHERE is_superadmin=1')
    if 'company_id' not in con.columns('groups'):
        con.execute("ALTER TABLE groups ADD COLUMN company_id TEXT NOT NULL DEFAULT 'default-company' REFERENCES companies(id) ON DELETE RESTRICT")
    con.execute('ALTER TABLE groups DROP CONSTRAINT IF EXISTS groups_name_key')
    con.execute('DROP INDEX IF EXISTS group_names')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS group_company_names ON groups(company_id,lower(name))')
    bind_superadmin(con)


def require_superadmin(current):
    if not current.get('is_superadmin'):
        raise HTTPException(403, 'Katalog firm jest dostępny tylko dla superadministratora.')
    return current


def company(con, identifier):
    row = con.execute('SELECT * FROM companies WHERE id=?', (identifier,)).fetchone()
    if not row:
        raise HTTPException(404, 'Nie znaleziono firmy.')
    return dict(row)


def account_company(con, current, requested=None):
    identifier = requested if requested is not None else current['company_id']
    if not current.get('is_superadmin') and identifier != current['company_id']:
        raise HTTPException(403, 'Tylko superadministrator może przypisać konto do innej firmy.')
    company(con, identifier)
    return identifier


def install(app, db, user):
    def superadmin(current=Depends(user)):
        return require_superadmin(current)

    @app.get('/api/me/company')
    def own_company(current=Depends(user)):
        with db() as con:
            return company(con, current['company_id'])

    @app.get('/api/admin/companies')
    def listing(current=Depends(superadmin)):
        with db() as con:
            return [dict(row) for row in con.execute('''SELECT c.*,
                (SELECT count(*) FROM users u WHERE u.company_id=c.id) AS user_count
                FROM companies c ORDER BY lower(c.name),c.id''')]

    @app.post('/api/admin/companies', status_code=201)
    def create(body: CompanyInput, current=Depends(superadmin)):
        try:
            with db() as con:
                con.begin_write()
                identifier = secrets.token_hex(16)
                con.execute('INSERT INTO companies(id,name,nip,address,email,phone) VALUES(?,?,?,?,?,?)',
                    (identifier, body.name, body.nip, body.address, body.email, body.phone))
                return company(con, identifier)
        except database.IntegrityError:
            raise HTTPException(409, 'Firma o tej nazwie już istnieje.') from None

    @app.patch('/api/admin/companies/{identifier}')
    def update(identifier: str, body: CompanyInput, current=Depends(superadmin)):
        try:
            with db() as con:
                con.begin_write()
                row = company(con, identifier)
                if body.version != row['version']:
                    raise HTTPException(409, 'Firma została zmieniona. Odśwież katalog przed edycją.')
                con.execute('UPDATE companies SET name=?,nip=?,address=?,email=?,phone=?,version=version+1 WHERE id=?',
                    (body.name, body.nip, body.address, body.email, body.phone, identifier))
                return company(con, identifier)
        except database.IntegrityError:
            raise HTTPException(409, 'Firma o tej nazwie już istnieje.') from None

    @app.delete('/api/admin/companies/{identifier}', status_code=204)
    def delete(identifier: str, current=Depends(superadmin)):
        with db() as con:
            con.begin_write()
            company(con, identifier)
            if identifier == DEFAULT_COMPANY_ID:
                raise HTTPException(409, 'Firmę domyślną można edytować, ale nie usuwać.')
            if con.execute('SELECT id FROM users WHERE company_id=? LIMIT 1', (identifier,)).fetchone() or con.execute('SELECT id FROM groups WHERE company_id=? LIMIT 1', (identifier,)).fetchone():
                raise HTTPException(409, 'Firma ma przypisane konta lub grupy. Przenieś konta i usuń grupy przed usunięciem firmy.')
            if con.execute('SELECT id FROM flow_definitions WHERE company_id=? LIMIT 1', (identifier,)).fetchone():
                raise HTTPException(409, 'Firma ma zapisane Flow. Usuń procesy przed usunięciem firmy.')
            con.execute('DELETE FROM companies WHERE id=?', (identifier,))
        return Response(status_code=204)
