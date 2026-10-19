"""Company-scoped workflow drafts. Saving a definition never executes its actions."""
import json
import secrets
from typing import Literal
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from backend import access

SCHEMA = """
CREATE TABLE IF NOT EXISTS flow_definitions(
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
 created_by TEXT REFERENCES users(id) ON DELETE SET NULL, name TEXT NOT NULL,
 description TEXT NOT NULL, trigger_config TEXT NOT NULL, steps TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS flow_company ON flow_definitions(company_id);
"""

class TriggerInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event: Literal['manual', 'email_received', 'document_added'] = 'manual'
    subject_contains: str = Field(default='', max_length=200)
    sender_contains: str = Field(default='', max_length=254)
    attachments_only: bool = False

class StepInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(default_factory=lambda: secrets.token_hex(8), min_length=1, max_length=64)
    kind: Literal['approval', 'task', 'save_document', 'notification']
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=2000)
    target_type: Literal['user', 'group'] = 'group'
    target_id: str | None = Field(default=None, min_length=1, max_length=100)
    folder_id: str | None = Field(default=None, min_length=1, max_length=100)
    due_days: int = Field(default=2, ge=1, le=365, strict=True)
    rejection: Literal['return', 'stop'] = 'return'

    @field_validator('title')
    @classmethod
    def clean_title(cls, value):
        if not value.strip(): raise ValueError('Podaj nazwę kroku.')
        return value.strip()

    @model_validator(mode='after')
    def required_target(self):
        if self.kind == 'save_document' and not self.folder_id:
            raise ValueError('Wybierz katalog dla zapisywanego dokumentu.')
        if self.kind != 'save_document' and not self.target_id:
            raise ValueError('Wybierz osobę lub grupę odpowiedzialną za krok.')
        return self

class FlowInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=2000)
    trigger: TriggerInput
    steps: list[StepInput] = Field(min_length=1, max_length=40)
    version: int | None = Field(default=None, ge=1, strict=True)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip(): raise ValueError('Podaj nazwę Flow.')
        return value.strip()

    @model_validator(mode='after')
    def unique_steps(self):
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError('Każdy krok musi mieć własny identyfikator.')
        return self


def install(app, db, user, now):
    def manager(current):
        if current['role'] != 'admin' or current.get('impersonation'):
            raise HTTPException(403, 'Flow może zmieniać administrator firmy na własnym koncie.')

    def owned(con, identifier, current):
        row = con.execute('SELECT * FROM flow_definitions WHERE id=? AND company_id=?',
                          (identifier, current['company_id'])).fetchone()
        if not row: raise HTTPException(404, 'Nie znaleziono Flow.')
        return row

    def result(row):
        item = dict(row)
        item['trigger'] = json.loads(item.pop('trigger_config'))
        item['steps'] = json.loads(item['steps'])
        item['status'] = 'draft'
        return item

    def validate_targets(con, body, current):
        for step in body.steps:
            if step.kind == 'save_document':
                folder = con.execute('SELECT f.* FROM folders f JOIN users u ON u.id=f.user_id WHERE f.id=? AND u.company_id=?',
                                     (step.folder_id, current['company_id'])).fetchone()
                if not folder or not access.permissions(con, current, folder['id'], folder['user_id'])['add']:
                    raise HTTPException(422, 'Wybierz dostępny katalog z uprawnieniem dodawania dokumentów.')
            elif step.target_type == 'user':
                if not con.execute('SELECT id FROM users WHERE id=? AND company_id=? AND active=1',
                                   (step.target_id, current['company_id'])).fetchone():
                    raise HTTPException(422, 'Wybrana osoba nie jest aktywnym użytkownikiem tej firmy.')
            elif not con.execute('SELECT id FROM groups WHERE id=? AND company_id=?',
                                 (step.target_id, current['company_id'])).fetchone():
                raise HTTPException(422, 'Wybrana grupa nie należy do tej firmy.')

    @app.get('/api/flows/options')
    def options(current=Depends(user)):
        with db() as con:
            folders = []
            for row in con.execute('SELECT f.* FROM folders f JOIN users u ON u.id=f.user_id WHERE u.company_id=? ORDER BY f.name', (current['company_id'],)):
                if access.permissions(con, current, row['id'], row['user_id'])['add']:
                    folders.append({'id': row['id'], 'name': row['name'], 'parent_id': row['parent_id']})
            return {'users': [dict(row) for row in con.execute('SELECT id,name FROM users WHERE company_id=? AND active=1 ORDER BY name', (current['company_id'],))],
                    'groups': [dict(row) for row in con.execute('SELECT id,name FROM groups WHERE company_id=? ORDER BY name', (current['company_id'],))], 'folders': folders}

    @app.get('/api/flows')
    def listing(current=Depends(user)):
        with db() as con:
            return [result(row) for row in con.execute('SELECT * FROM flow_definitions WHERE company_id=? ORDER BY updated_at DESC,id', (current['company_id'],))]

    @app.post('/api/flows', status_code=201)
    def create(body: FlowInput, current=Depends(user)):
        manager(current)
        with db() as con:
            con.begin_write()
            validate_targets(con, body, current)
            identifier, timestamp = secrets.token_hex(16), now()
            con.execute('INSERT INTO flow_definitions(id,company_id,created_by,name,description,trigger_config,steps,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                        (identifier, current['company_id'], current['id'], body.name, body.description.strip(), json.dumps(body.trigger.model_dump()), json.dumps([step.model_dump() for step in body.steps]), timestamp, timestamp))
            return result(owned(con, identifier, current))

    @app.put('/api/flows/{identifier}')
    def update(identifier: str, body: FlowInput, current=Depends(user)):
        manager(current)
        with db() as con:
            con.begin_write()
            row = owned(con, identifier, current)
            if body.version != row['version']: raise HTTPException(409, 'Flow zostało zmienione. Otwórz je ponownie przed zapisem.')
            validate_targets(con, body, current)
            con.execute('UPDATE flow_definitions SET name=?,description=?,trigger_config=?,steps=?,version=version+1,updated_at=? WHERE id=? AND company_id=?',
                        (body.name, body.description.strip(), json.dumps(body.trigger.model_dump()), json.dumps([step.model_dump() for step in body.steps]), now(), identifier, current['company_id']))
            return result(owned(con, identifier, current))

    @app.delete('/api/flows/{identifier}', status_code=204)
    def remove(identifier: str, version: int, current=Depends(user)):
        manager(current)
        with db() as con:
            con.begin_write()
            row = owned(con, identifier, current)
            if version != row['version']: raise HTTPException(409, 'Flow zostało zmienione. Odśwież listę przed usunięciem.')
            con.execute('DELETE FROM flow_definitions WHERE id=? AND company_id=?', (identifier, current['company_id']))
        return Response(status_code=204)
