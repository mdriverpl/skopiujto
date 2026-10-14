import secrets
import json
from backend import database
from typing import Literal

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

class GroupInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)

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

    def group(con, group_id):
        row = con.execute('SELECT * FROM groups WHERE id=?', (group_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Nie znaleziono grupy.')
        return row

    @app.get('/api/admin/users')
    def users(current=Depends(admin)):
        with db() as con:
            return [public_account(row) for row in con.execute('SELECT * FROM users ORDER BY name')]

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
                if con.execute('SELECT 1 FROM users WHERE lower(name)=lower(?)', (name,)).fetchone():
                    raise HTTPException(409, 'Użytkownik o tej nazwie już istnieje.')
                con.execute('INSERT INTO users(id,name,password,role,active,can_read,can_edit,can_add,can_delete,email,must_change_password) VALUES(?,?,?,?,1,?,?,?,?,?,1)',
                            (uid,name,password_hash(temporary_password),body.role,body.can_read or body.can_edit or body.can_add or body.can_delete,body.can_edit,body.can_add,body.can_delete,email))
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
            if not row:
                raise HTTPException(404, 'Nie znaleziono użytkownika.')
            if current['id'] == user_id and (changes.get('active') is False or changes.get('role') == 'user'):
                raise HTTPException(409, 'Nie możesz dezaktywować swojego konta ani odebrać sobie roli administratora.')
            if row['role'] == 'admin' and row['active'] and (changes.get('active') is False or changes.get('role') == 'user'):
                count = con.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
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
            if 'password' in changes or changes.get('active') is False:
                con.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
                con.execute('DELETE FROM api_access_tokens WHERE user_id=?', (user_id,))
            return public_account(con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())

    @app.get('/api/admin/groups')
    def groups(current=Depends(admin)):
        with db() as con:
            result = []
            for row in con.execute('SELECT * FROM groups ORDER BY name'):
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
                con.execute('INSERT INTO groups VALUES(?,?)', (gid,name))
        except database.IntegrityError:
            raise HTTPException(409, 'Grupa o tej nazwie już istnieje.') from None
        return {'id': gid, 'name': name, 'members': [], 'permissions': []}

    @app.delete('/api/admin/groups/{group_id}', status_code=204)
    def delete_group(group_id: str, current=Depends(admin)):
        with db() as con:
            group(con, group_id)
            con.execute('DELETE FROM groups WHERE id=?', (group_id,))

    @app.put('/api/admin/groups/{group_id}/members/{user_id}', status_code=204)
    def add_member(group_id: str, user_id: str, current=Depends(admin)):
        with db() as con:
            group(con, group_id)
            if not con.execute('SELECT 1 FROM users WHERE id=?', (user_id,)).fetchone():
                raise HTTPException(404, 'Nie znaleziono użytkownika.')
            con.execute('INSERT INTO group_members VALUES(?,?) ON CONFLICT DO NOTHING', (group_id,user_id))

    @app.delete('/api/admin/groups/{group_id}/members/{user_id}', status_code=204)
    def remove_member(group_id: str, user_id: str, current=Depends(admin)):
        with db() as con:
            group(con, group_id)
            con.execute('DELETE FROM group_members WHERE group_id=? AND user_id=?', (group_id,user_id))

    @app.get('/api/admin/folders')
    def all_folders(current=Depends(admin)):
        with db() as con:
            return [dict(row) for row in con.execute('SELECT f.*,u.name AS owner_name FROM folders f JOIN users u ON u.id=f.user_id ORDER BY f.name')]

    @app.put('/api/admin/groups/{group_id}/permissions')
    def set_permissions(group_id: str, body: GrantInput, current=Depends(admin)):
        with db() as con:
            con.begin_write()
            group(con, group_id)
            if body.folder_id is not None and not con.execute('SELECT 1 FROM folders WHERE id=?', (body.folder_id,)).fetchone():
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
