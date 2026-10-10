from backend import database
"""Assigned work and existing file approvals in one personal task view."""
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from backend import access, mailing

SCHEMA = '''
CREATE TABLE IF NOT EXISTS user_tasks(
  id TEXT PRIMARY KEY, sender_id TEXT NOT NULL REFERENCES users(id),
  assignee_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
  description TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'todo',
  document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
  folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL, due_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT,
  version INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS user_tasks_assignee ON user_tasks(assignee_id);
CREATE INDEX IF NOT EXISTS user_tasks_sender ON user_tasks(sender_id);
'''


def initialize(con):
    con.executescript(SCHEMA)
    if 'folder_id' not in database.columns(con, 'user_tasks'):
        con.execute('ALTER TABLE user_tasks ADD COLUMN folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL')


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=5000)
    assignee_id: str = Field(min_length=1, max_length=100)
    kind: Literal['general', 'signature', 'modification'] = 'general'
    document_id: str | None = Field(default=None, max_length=100)
    folder_id: str | None = Field(default=None, max_length=100)
    due_at: datetime | None = None

    @model_validator(mode='after')
    def single_resource(self):
        if self.document_id is not None and self.folder_id is not None:
            raise ValueError('Wybierz plik albo katalog.')
        if self.document_id == '' or self.folder_id == '':
            raise ValueError('Wybierz powiązany plik lub katalog.')
        return self

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip(): raise ValueError('Podaj tytuł zadania.')
        return value.strip()

    @field_validator('due_at')
    @classmethod
    def aware_time(cls, value):
        if value and value.tzinfo is None: raise ValueError('Termin musi zawierać strefę czasową.')
        return value.astimezone(timezone.utc) if value else None


class StatusInput(BaseModel):
    status: Literal['in_progress', 'done', 'cancelled']
    version: int = Field(strict=True, ge=1)


def install(app, db, user, owned, now):
    def details(con, row, current):
        item = dict(row)
        item.update(origin='task', key='task:' + row['id'], filename=None,
                    can_update=row['assignee_id'] == current['id'] and row['status'] in ('todo', 'in_progress'),
                    can_cancel=row['sender_id'] == current['id'] and row['status'] in ('todo', 'in_progress'))
        doc = con.execute('SELECT id,user_id,folder_id,filename,uploaded_by,title,status,version,created_at FROM documents WHERE id=?', (row['document_id'],)).fetchone() if row['document_id'] else None
        if doc and access.document_permissions(con, current, doc)['read']:
            item.update(document_title=doc['title'], filename=doc['filename'])
        else:
            item.update(document_id=None, document_title=None)
        folder = con.execute('SELECT id,name,user_id FROM folders WHERE id=?', (row['folder_id'],)).fetchone() if row['folder_id'] else None
        if folder and access.permissions(con, current, folder['id'], folder['user_id'])['read']:
            item.update(folder_name=folder['name'])
        else:
            item.update(folder_id=None, folder_name=None)
        return item

    def assigned(con, identifier, current):
        row = con.execute('''SELECT t.*,s.name AS sender_name,a.name AS assignee_name FROM user_tasks t
          JOIN users s ON s.id=t.sender_id JOIN users a ON a.id=t.assignee_id
          WHERE t.id=? AND (t.sender_id=? OR t.assignee_id=?)''',
                          (identifier, current['id'], current['id'])).fetchone()
        if not row: raise HTTPException(404, 'Nie znaleziono zadania.')
        return row

    @app.get('/api/tasks')
    def listing(current=Depends(user)):
        with db() as con:
            mine, sent = [], []
            rows = con.execute('''SELECT t.*,s.name AS sender_name,a.name AS assignee_name FROM user_tasks t
              JOIN users s ON s.id=t.sender_id JOIN users a ON a.id=t.assignee_id
              WHERE t.sender_id=? OR t.assignee_id=?''', (current['id'], current['id'])).fetchall()
            for row in rows:
                item = details(con, row, current)
                if row['assignee_id'] == current['id']: mine.append(item)
                if row['sender_id'] == current['id']: sent.append(item)
            approvals = con.execute('''SELECT r.*,m.document_id,m.title,m.filename,m.version AS file_version,
              m.sender_id,m.sender_name,m.message,m.created_at,m.expires FROM file_mail_recipients r
              JOIN file_mailings m ON m.id=r.mailing_id JOIN users s ON s.id=m.sender_id
              WHERE (r.channel='user' AND r.user_id=? AND s.active=1) OR m.sender_id=?''',
                                   (current['id'], current['id'])).fetchall()
            for row in approvals:
                status = mailing.recipient_status(row, row['expires'])
                item = {'id': row['id'], 'key': 'approval:' + row['id'], 'origin': 'approval', 'kind': 'approval',
                    'title': row['title'], 'description': row['message'], 'filename': row['filename'],
                    'file_version': row['file_version'], 'sender_id': row['sender_id'], 'sender_name': row['sender_name'],
                    'assignee_id': row['user_id'], 'assignee_name': row['name'] or row['phone'] or row['email'],
                    'channel': row['channel'], 'status': status, 'due_at': datetime.fromtimestamp(row['expires'], timezone.utc).isoformat(),
                    'created_at': row['created_at'], 'completed_at': row['accepted_at'],
                    'can_accept': row['channel'] == 'user' and row['user_id'] == current['id'] and status == 'waiting',
                    'can_download': row['channel'] == 'user' and row['user_id'] == current['id'] and
                                    status in ('waiting', 'accepted') and row['expires'] > datetime.now(timezone.utc).timestamp(),
                    'can_update': False, 'can_cancel': False, 'document_id': None}
                if row['channel'] == 'user' and row['user_id'] == current['id']: mine.append(item)
                if row['sender_id'] == current['id']:
                    doc = con.execute('SELECT id,user_id,folder_id,filename,uploaded_by,title,status,version,created_at FROM documents WHERE id=?', (row['document_id'],)).fetchone()
                    sent.append({**item, 'document_id': doc['id'] if doc and access.document_permissions(con, current, doc)['read'] else None})
            # Own documents already marked for action belong here without creating duplicate DB tasks.
            for doc in con.execute("SELECT id,user_id,folder_id,filename,uploaded_by,title,status,version,created_at FROM documents WHERE user_id=? AND status IN ('Do podpisania','Do modyfikacji','Do akceptacji','W toku')", (current['id'],)):
                rights = access.document_permissions(con, current, doc)
                if not rights['read']: continue
                kind = {'Do podpisania': 'signature', 'Do modyfikacji': 'modification', 'Do akceptacji': 'approval'}.get(doc['status'], 'general')
                mine.append({'id': doc['id'], 'key': 'document:' + doc['id'], 'origin': 'document', 'kind': kind,
                    'title': doc['title'], 'description': doc['status'], 'document_id': doc['id'], 'filename': doc['filename'],
                    'sender_name': current['name'], 'assignee_name': current['name'], 'status': 'in_progress' if doc['status'] == 'W toku' else 'todo',
                    'created_at': doc['created_at'], 'can_update': False, 'can_cancel': False})
            for doc in con.execute("SELECT id,user_id,folder_id,filename,uploaded_by,title,status,version,created_at FROM documents WHERE user_id=? AND status!='Archiwum'", (current['id'],)):
                rights = access.document_permissions(con, current, doc)
                if not rights['read']: continue
                for deadline in con.execute('SELECT * FROM deadlines WHERE document_id=?', (doc['id'],)):
                    mine.append({'id': deadline['id'], 'key': 'deadline:' + deadline['id'], 'origin': 'deadline',
                        'kind': 'deadline', 'title': deadline['title'], 'description': doc['title'], 'document_id': doc['id'],
                        'filename': doc['filename'], 'sender_name': current['name'], 'assignee_name': current['name'],
                        'status': 'done' if deadline['done'] else 'todo', 'due_at': deadline['due_at'],
                        'created_at': doc['created_at'], 'can_update': bool(rights['edit'] and not deadline['done']), 'can_cancel': False})
            for items in (mine, sent): items.sort(key=lambda item: (item['created_at'], item['key']), reverse=True)
            return {'mine': mine, 'sent': sent, 'waiting': sum(item['status'] in ('todo', 'in_progress', 'waiting', 'sending') for item in mine)}

    @app.post('/api/tasks', status_code=201)
    def create(body: TaskInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            target = con.execute('SELECT * FROM users WHERE id=? AND active=1', (body.assignee_id,)).fetchone()
            if not target: raise HTTPException(422, 'Wybierz aktywnego użytkownika.')
            if body.folder_id:
                folder = con.execute('SELECT id,user_id FROM folders WHERE id=?', (body.folder_id,)).fetchone()
                if not folder or not access.permissions(con, current, folder['id'], folder['user_id'])['read']:
                    raise HTTPException(404, 'Nie znaleziono katalogu.')
                if not access.permissions(con, dict(target), folder['id'], folder['user_id'])['read']:
                    raise HTTPException(422, 'Odbiorca nie ma dostępu do katalogu. Najpierw udostępnij mu katalog.')
            if body.document_id:
                doc = owned(con, body.document_id, current)
                rights = access.document_permissions(con, dict(target), doc)
                if not rights['read']:
                    raise HTTPException(422, 'Odbiorca nie ma dostępu do dokumentu. Najpierw udostępnij mu folder lub wyślij plik do akceptacji.')
                if body.kind == 'modification' and not rights['edit']:
                    raise HTTPException(422, 'Odbiorca nie ma uprawnienia do edycji tego dokumentu.')
            identifier = secrets.token_hex(16)
            con.execute('''INSERT INTO user_tasks(id,sender_id,assignee_id,title,description,kind,document_id,folder_id,due_at,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (identifier, current['id'], body.assignee_id, body.title, body.description.strip(),
                body.kind, body.document_id, body.folder_id, body.due_at.isoformat() if body.due_at else None, now(), now()))
            return details(con, assigned(con, identifier, current), current)

    @app.patch('/api/tasks/{identifier}/status')
    def update(identifier: str, body: StatusInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = assigned(con, identifier, current)
            expected_user = row['sender_id'] if body.status == 'cancelled' else row['assignee_id']
            if expected_user != current['id']: raise HTTPException(403, 'Tę zmianę może wykonać tylko właściwy uczestnik zadania.')
            if row['version'] != body.version: raise HTTPException(409, 'Zadanie zostało zmienione. Odśwież listę.')
            if row['status'] not in ('todo', 'in_progress'): raise HTTPException(409, 'Zadanie jest już zakończone lub anulowane.')
            con.execute('UPDATE user_tasks SET status=?,updated_at=?,completed_at=?,version=version+1 WHERE id=?',
                        (body.status, now(), now() if body.status == 'done' else None, identifier))
            return details(con, assigned(con, identifier, current), current)
