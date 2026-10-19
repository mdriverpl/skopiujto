import secrets
import json
from backend import database, companies
from typing import Literal
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from backend import audit
from backend import mailer
from email_validator import validate_email, EmailNotValidError

class AccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(max_length=254)
    role: Literal['admin', 'user'] = 'user'
    can_read: bool = True
    can_edit: bool = False
    can_add: bool = False
    can_delete: bool = False
    company_id: str | None = Field(default=None, min_length=1, max_length=100)

class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    password: str | None = Field(default=None, min_length=10, max_length=200)
    role: Literal['admin', 'user'] | None = None
    active: bool | None = None
    can_read: bool | None = None
    can_edit: bool | None = None
    can_add: bool | None = None
    can_delete: bool | None = None
    company_id: str | None = Field(default=None, min_length=1, max_length=100)

class GroupInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    company_id: str | None = Field(default=None, min_length=1, max_length=100)

class GrantInput(BaseModel):
    folder_id: str | None = None
    can_read: bool = True
    can_edit: bool = False
    can_add: bool = False
    can_delete: bool = False

def public_account(row):
    data = dict(row)
    data.pop('password', None)
    data['menu_order'] = json.loads(data.get('menu_order', '[]'))
    for key in ('active', 'can_read', 'can_edit', 'can_add', 'can_delete', 'must_change_password'):
        data[key] = bool(data[key])
    data['is_superadmin'] = bool(data.get('is_superadmin', False))
    return data

def account_email(value):
    try:
        return validate_email(value.strip(), check_deliverability=False, allow_smtputf8=False).ascii_email
    except EmailNotValidError:
        raise HTTPException(422, 'Podaj poprawny adres e-mail użytkownika.') from None

def install(app, db, user, password_hash):
    def admin(current=Depends(user)):
        if current['role'] != 'admin':
            raise HTTPException(403, 'Panel jest dostępny tylko dla administratora.')
        return current

    def group(con, group_id, current):
        row = con.execute('SELECT * FROM groups WHERE id=?', (group_id,)).fetchone()
        if not row or row.get('deleted_at') or (not current.get('is_superadmin') and row['company_id'] != current['company_id']):
            raise HTTPException(404, 'Nie znaleziono grupy.')
        return row

    @app.get('/api/admin/users')
    def users(include_deleted: bool = False, current=Depends(admin)):
        with db() as con:
            query = 'SELECT u.*,c.name AS company_name FROM users u JOIN companies c ON c.id=u.company_id WHERE 1=1'
            if not include_deleted: query += ' AND u.deleted_at IS NULL'
            params = ()
            if not current.get('is_superadmin'):
                query += ' AND u.company_id=?'; params = (current['company_id'],)
            return [public_account(row) for row in con.execute(query + ' ORDER BY u.name', params)]

    @app.post('/api/admin/users', status_code=201)
    def create_user(body: AccountCreate, current=Depends(admin)):
        name = body.name.strip()
        if len(name) < 2:
            raise HTTPException(422, 'Nazwa użytkownika musi mieć co najmniej 2 znaki.')
        uid = secrets.token_hex(16)
        email = account_email(body.email)
        config = mailer.configuration()
        temporary_password = secrets.token_urlsafe(18)
        try:
            with db() as con:
                con.begin_write()
                company_id = companies.account_company(con, current, body.company_id)
                if con.execute('SELECT 1 FROM users WHERE lower(name)=lower(?)', (name,)).fetchone():
                    raise HTTPException(409, 'Użytkownik o tej nazwie już istnieje.')
                con.execute('INSERT INTO users(id,name,password,role,active,can_read,can_edit,can_add,can_delete,email,must_change_password,company_id) VALUES(?,?,?,?,1,?,?,?,?,?,1,?)',
                            (uid,name,password_hash(temporary_password),body.role,body.can_read or body.can_edit or body.can_add or body.can_delete,body.can_edit,body.can_add,body.can_delete,email,company_id))
                mailer.send_message(config, email, 'eDokumenty', 'Twoje konto w eDokumentach',
                    f'Utworzono Twoje konto w eDokumentach.\n\nAdres aplikacji: {config["public_url"]}\n'
                    f'Nazwa użytkownika: {name}\nHasło tymczasowe: {temporary_password}\n\n'
                    'Przy pierwszym logowaniu musisz ustawić własne hasło. Nie przekazuj tej wiadomości innym osobom.')
                return public_account(con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())
        except database.IntegrityError:
            raise HTTPException(409, 'Użytkownik o tej nazwie już istnieje.') from None

    @app.patch('/api/admin/users/{user_id}')
    def update_user(user_id: str, body: AccountUpdate, current=Depends(admin)):
        changes = body.model_dump(exclude_none=True)
        with db() as con:
            con.begin_write()
            row = con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if not row or row.get('deleted_at') or (not current.get('is_superadmin') and (row['company_id'] != current['company_id'] or row['is_superadmin'])):
                raise HTTPException(404, 'Nie znaleziono użytkownika.')
            if row['is_superadmin'] and (changes.get('role') == 'user' or changes.get('active') is False):
                raise HTTPException(409, 'Nie można zablokować ani zdegradować jedynego superadministratora.')
            if 'company_id' in changes:
                changes['company_id'] = companies.account_company(con, current, changes['company_id'])
                if changes['company_id'] != row['company_id']:
                    con.execute('DELETE FROM group_members WHERE user_id=?', (user_id,))
            if current['id'] == user_id and (changes.get('active') is False or changes.get('role') == 'user'):
                raise HTTPException(409, 'Nie możesz dezaktywować swojego konta ani odebrać sobie roli administratora.')
            if row['role'] == 'admin' and row['active'] and (changes.get('active') is False or changes.get('role') == 'user'):
                count = con.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1 AND company_id=?", (row['company_id'],)).fetchone()[0]
                if count <= 1:
                    raise HTTPException(409, 'Musi pozostać co najmniej jeden aktywny administrator.')
            if 'name' in changes:
                changes['name'] = changes['name'].strip()
                if len(changes['name']) < 2:
                    raise HTTPException(422, 'Nazwa użytkownika musi mieć co najmniej 2 znaki.')
                if con.execute('SELECT 1 FROM users WHERE lower(name)=lower(?) AND id!=?', (changes['name'],user_id)).fetchone():
                    raise HTTPException(409, 'Użytkownik o tej nazwie już istnieje.')
            if 'password' in changes:
                changes['password'] = password_hash(changes['password'])
                changes['must_change_password'] = True
            if 'email' in changes:
                changes['email'] = account_email(changes['email']) if changes['email'].strip() else None
            if any(changes.get('can_' + action, bool(row['can_' + action])) for action in ('edit', 'add', 'delete')):
                changes['can_read'] = True
            for key, value in changes.items():
                con.execute(f'UPDATE users SET {key}=? WHERE id=?', (value,user_id))
            if 'password' in changes or changes.get('active') is False or ('company_id' in changes and changes['company_id'] != row['company_id']):
                con.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
                con.execute('DELETE FROM api_access_tokens WHERE user_id=?', (user_id,))
                con.execute('DELETE FROM impersonation_sessions WHERE target_id=?', (user_id,))
            return public_account(con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())

    @app.delete('/api/admin/users/{user_id}', status_code=204)
    def delete_user(user_id: str, current=Depends(admin)):
        try:
            with db() as con:
                con.begin_write()
                row = con.execute('SELECT * FROM users WHERE id=? FOR UPDATE', (user_id,)).fetchone()
                if not row or row.get('deleted_at') or (not current.get('is_superadmin') and row['company_id'] != current['company_id']):
                    raise HTTPException(404, 'Nie znaleziono użytkownika.')
                if row['is_superadmin']:
                    raise HTTPException(409, 'Nie można usunąć superadministratora.')
                if current['id'] == user_id:
                    raise HTTPException(409, 'Nie możesz usunąć swojego konta.')
                if row['role'] == 'admin' and row['active']:
                    count = con.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1 AND company_id=?", (row['company_id'],)).fetchone()[0]
                    if count <= 1:
                        raise HTTPException(409, 'Musi pozostać co najmniej jeden aktywny administrator firmy.')
                # Retain the owner identity and every foreign-key relationship for archived records.
                con.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
                con.execute('DELETE FROM api_access_tokens WHERE user_id=?', (user_id,))
                con.execute('DELETE FROM impersonation_sessions WHERE target_id=? OR actor_id=?', (user_id, user_id))
                con.execute('DELETE FROM group_members WHERE user_id=?', (user_id,))
                con.execute('DELETE FROM folder_user_permissions WHERE user_id=?', (user_id,))
                con.execute('UPDATE users SET active=0,deleted_at=?,password=? WHERE id=?',
                            (datetime.now(timezone.utc).isoformat(), password_hash(secrets.token_urlsafe(48)), user_id))
        except database.IntegrityError:
            raise HTTPException(409, 'Nie udało się usunąć konta. Żadne dokumenty ani uprawnienia nie zostały zmienione.') from None

    @app.get('/api/admin/groups')
    def groups(current=Depends(admin)):
        with db() as con:
            result = []
            query, params = ('SELECT * FROM groups ORDER BY name', ()) if current.get('is_superadmin') else ('SELECT * FROM groups WHERE company_id=? ORDER BY name', (current['company_id'],))
            for row in con.execute(query, params):
                item = dict(row)
                item['members'] = [r[0] for r in con.execute('SELECT user_id FROM group_members WHERE group_id=?', (row['id'],))]
                item['permissions'] = [dict(r) for r in con.execute('SELECT * FROM group_permissions WHERE group_id=?', (row['id'],))]
                result.append(item)
            return result

    @app.post('/api/admin/groups', status_code=201)
    def create_group(body: GroupInput, current=Depends(admin)):
        name = body.name.strip()
        if not name:
            raise HTTPException(422, 'Podaj nazwę grupy.')
        gid = secrets.token_hex(16)
        try:
            with db() as con:
                company_id = companies.account_company(con, current, body.company_id)
                con.execute('INSERT INTO groups(id,name,company_id) VALUES(?,?,?)', (gid,name,company_id))
        except database.IntegrityError:
            raise HTTPException(409, 'Grupa o tej nazwie już istnieje.') from None
        return {'id': gid, 'name': name, 'company_id': company_id, 'members': [], 'permissions': []}

    @app.delete('/api/admin/groups/{group_id}', status_code=204)
    def delete_group(group_id: str, current=Depends(admin)):
        with db() as con:
            group(con, group_id, current)
            con.execute('DELETE FROM groups WHERE id=?', (group_id,))

    @app.put('/api/admin/groups/{group_id}/members/{user_id}', status_code=204)
    def add_member(group_id: str, user_id: str, current=Depends(admin)):
        with db() as con:
            selected_group = group(con, group_id, current)
            if not con.execute('SELECT 1 FROM users WHERE id=? AND company_id=?', (user_id,selected_group['company_id'])).fetchone():
                raise HTTPException(404, 'Nie znaleziono użytkownika.')
            con.execute('INSERT INTO group_members VALUES(?,?) ON CONFLICT DO NOTHING', (group_id,user_id))

    @app.delete('/api/admin/groups/{group_id}/members/{user_id}', status_code=204)
    def remove_member(group_id: str, user_id: str, current=Depends(admin)):
        with db() as con:
            group(con, group_id, current)
            con.execute('DELETE FROM group_members WHERE group_id=? AND user_id=?', (group_id,user_id))

    @app.get('/api/admin/folders')
    def all_folders(current=Depends(admin)):
        with db() as con:
            query = 'SELECT f.*,u.name AS owner_name,u.company_id FROM folders f JOIN users u ON u.id=f.user_id'
            params = ()
            if not current.get('is_superadmin'):
                query += ' AND u.company_id=?'; params = (current['company_id'],)
            return [dict(row) for row in con.execute(query + ' ORDER BY f.name', params)]

    @app.put('/api/admin/groups/{group_id}/permissions')
    def set_permissions(group_id: str, body: GrantInput, current=Depends(admin)):
        with db() as con:
            con.begin_write()
            selected_group = group(con, group_id, current)
            if body.folder_id is not None and not con.execute('SELECT 1 FROM folders f JOIN users u ON u.id=f.user_id WHERE f.id=? AND u.company_id=?', (body.folder_id,selected_group['company_id'])).fetchone():
                raise HTTPException(404, 'Nie znaleziono folderu.')
            scope = body.folder_id if body.folder_id is not None else 'root'
            values = [body.can_read or body.can_edit or body.can_add or body.can_delete, body.can_edit, body.can_add, body.can_delete]
            previous = con.execute('SELECT can_read,can_edit,can_add,can_delete FROM group_permissions WHERE group_id=? AND scope=?', (group_id, scope)).fetchone()
            if not any(values):
                con.execute('DELETE FROM group_permissions WHERE group_id=? AND scope=?', (group_id,scope))
            else:
                con.execute('INSERT INTO group_permissions VALUES(?,?,?,?,?,?,?) ON CONFLICT(group_id,scope) DO UPDATE SET can_read=excluded.can_read,can_edit=excluded.can_edit,can_add=excluded.can_add,can_delete=excluded.can_delete',
                            (group_id,scope,body.folder_id,*values))
            if body.folder_id is not None:
                old = [bool(previous[key]) for key in ('can_read', 'can_edit', 'can_add', 'can_delete')] if previous else [False] * 4
                if old != [bool(value) for value in values]:
                    folder = con.execute('SELECT * FROM folders WHERE id=?', (body.folder_id,)).fetchone()
                    group_name = con.execute('SELECT name FROM groups WHERE id=?', (group_id,)).fetchone()['name']
                    names = ('Odczyt', 'Edycja', 'Dodawanie', 'Usuwanie')
                    audit.record(con, current, 'folder', folder, 'Zmieniono uprawnienia grupy', [audit.change('permissions',
                        {'grupa': group_name, **dict(zip(names, old))}, {'grupa': group_name, **dict(zip(names, map(bool, values)))})])
        return {'scope': scope, 'can_read': bool(values[0]), 'can_edit': body.can_edit, 'can_add': body.can_add, 'can_delete': body.can_delete}
