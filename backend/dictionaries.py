from backend import database
"""Private dictionaries with user-defined columns and versioned entries."""
import json
import secrets
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from backend.document_fields import key

SCHEMA = '''
CREATE TABLE IF NOT EXISTS dictionaries(
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 name TEXT NOT NULL,fields TEXT NOT NULL,created_at TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
CREATE UNIQUE INDEX IF NOT EXISTS dictionary_names ON dictionaries(user_id,lower(name));
CREATE TABLE IF NOT EXISTS dictionary_entries(
 id TEXT PRIMARY KEY,dictionary_id TEXT NOT NULL REFERENCES dictionaries(id) ON DELETE CASCADE,
 values_json TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS dictionary_entry_parent ON dictionary_entries(dictionary_id);
'''

def initialize(con):
    con.executescript(SCHEMA)
    if 'version' not in database.columns(con, 'dictionaries'):
        con.execute('ALTER TABLE dictionaries ADD COLUMN version INTEGER NOT NULL DEFAULT 1')

class DictionaryInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    fields: list[str] = Field(min_length=1, max_length=60)

    @field_validator('name')
    @classmethod
    def name_valid(cls, value):
        value = value.strip()
        if not value or value.casefold() == 'ai': raise ValueError('Wybierz nazwę słownika inną niż AI.')
        return value

    @field_validator('fields')
    @classmethod
    def fields_valid(cls, values):
        labels = [value.strip() for value in values]
        if any(not label or len(label) > 80 or any(c in label for c in '[]\r\n') for label in labels):
            raise ValueError('Podaj nazwy pól, maksymalnie 80 znaków.')
        if len({key(label) for label in labels}) != len(labels): raise ValueError('Nazwy pól nie mogą się powtarzać.')
        return labels

class EntryInput(BaseModel):
    values: dict[str, str] = Field(min_length=1, max_length=60)
    version: int | None = Field(default=None, strict=True, ge=1)

class DictionaryUpdate(DictionaryInput):
    version: int = Field(strict=True, ge=1)
    field_sources: dict[str, str | None] = Field(max_length=60)

def install(app, db, user, now):
    def owned(con, identifier, current):
        row = con.execute('SELECT * FROM dictionaries WHERE id=? AND user_id=?', (identifier, current['id'])).fetchone()
        if not row: raise HTTPException(404, 'Nie znaleziono słownika.')
        return row

    def dictionary(con, row):
        return {'id': row['id'], 'name': row['name'], 'fields': json.loads(row['fields']), 'version': row['version'],
            'count': con.execute('SELECT count(*) FROM dictionary_entries WHERE dictionary_id=?', (row['id'],)).fetchone()[0]}

    def entry(row):
        return {'id': row['id'], 'values': json.loads(row['values_json']), 'version': row['version'], 'updated_at': row['updated_at']}

    def values(body, row):
        fields = json.loads(row['fields'])
        if set(body.values) - set(fields): raise HTTPException(422, 'Dane zawierają pole spoza słownika.')
        if any(len(value) > 2000 for value in body.values.values()): raise HTTPException(422, 'Wartość jest za długa.')
        result = {field: body.values.get(field, '').strip() for field in fields}
        if not any(result.values()): raise HTTPException(422, 'Uzupełnij co najmniej jedno pole.')
        return json.dumps(result, ensure_ascii=False)

    @app.get('/api/dictionaries')
    def listing(current=Depends(user)):
        with db() as con:
            return [dictionary(con, row) for row in con.execute('SELECT * FROM dictionaries WHERE user_id=? ORDER BY lower(name)', (current['id'],))]

    @app.post('/api/dictionaries', status_code=201)
    def create(body: DictionaryInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            if con.execute('SELECT 1 FROM dictionaries WHERE user_id=? AND lower(name)=lower(?)', (current['id'], body.name)).fetchone():
                raise HTTPException(409, 'Słownik o tej nazwie już istnieje.')
            identifier = secrets.token_hex(16)
            con.execute('INSERT INTO dictionaries(id,user_id,name,fields,created_at) VALUES(?,?,?,?,?)', (identifier, current['id'], body.name, json.dumps(body.fields, ensure_ascii=False), now()))
            return dictionary(con, owned(con, identifier, current))

    @app.put('/api/dictionaries/{identifier}')
    def update(identifier: str, body: DictionaryUpdate, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = owned(con, identifier, current)
            if row['version'] != body.version: raise HTTPException(409, 'Słownik został zmieniony. Odśwież listę.')
            if con.execute('SELECT 1 FROM dictionaries WHERE user_id=? AND lower(name)=lower(?) AND id!=?', (current['id'], body.name, identifier)).fetchone():
                raise HTTPException(409, 'Słownik o tej nazwie już istnieje.')
            old_fields = json.loads(row['fields'])
            sources = [body.field_sources.get(field) for field in body.fields]
            existing = [source for source in sources if source is not None]
            if set(body.field_sources) != set(body.fields) or set(existing) - set(old_fields) or len(set(existing)) != len(existing):
                raise HTTPException(422, 'Nieprawidłowe powiązanie pól słownika.')
            changed = body.fields != old_fields or sources != old_fields
            if changed:
                for item in con.execute('SELECT * FROM dictionary_entries WHERE dictionary_id=?', (identifier,)).fetchall():
                    old_values = json.loads(item['values_json'])
                    updated = {field: old_values.get(source, '') if source is not None else '' for field, source in zip(body.fields, sources)}
                    con.execute('UPDATE dictionary_entries SET values_json=?,version=version+1,updated_at=? WHERE id=?',
                                (json.dumps(updated, ensure_ascii=False), now(), item['id']))
            con.execute('UPDATE dictionaries SET name=?,fields=?,version=version+1 WHERE id=?', (body.name, json.dumps(body.fields, ensure_ascii=False), identifier))
            return {'dictionary': dictionary(con, owned(con, identifier, current)), 'entries': [entry(item) for item in con.execute(
                'SELECT * FROM dictionary_entries WHERE dictionary_id=? ORDER BY updated_at DESC,id', (identifier,))]}

    @app.delete('/api/dictionaries/{identifier}', status_code=204)
    def remove(identifier: str, current=Depends(user)):
        with db() as con:
            owned(con, identifier, current)
            con.execute('DELETE FROM dictionaries WHERE id=?', (identifier,))
        return Response(status_code=204)

    @app.get('/api/dictionaries/{identifier}/entries')
    def entries(identifier: str, current=Depends(user)):
        with db() as con:
            row = owned(con, identifier, current)
            return {'dictionary': dictionary(con, row), 'entries': [entry(item) for item in con.execute(
                'SELECT * FROM dictionary_entries WHERE dictionary_id=? ORDER BY updated_at DESC,id', (identifier,))]}

    @app.post('/api/dictionaries/{identifier}/entries', status_code=201)
    def add(identifier: str, body: EntryInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = owned(con, identifier, current)
            entry_id = secrets.token_hex(16)
            con.execute('INSERT INTO dictionary_entries(id,dictionary_id,values_json,updated_at) VALUES(?,?,?,?)', (entry_id, identifier, values(body, row), now()))
            return entry(con.execute('SELECT * FROM dictionary_entries WHERE id=?', (entry_id,)).fetchone())

    @app.put('/api/dictionaries/{identifier}/entries/{entry_id}')
    def edit(identifier: str, entry_id: str, body: EntryInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = owned(con, identifier, current)
            item = con.execute('SELECT * FROM dictionary_entries WHERE id=? AND dictionary_id=?', (entry_id, identifier)).fetchone()
            if not item: raise HTTPException(404, 'Nie znaleziono wpisu.')
            if item['version'] != body.version: raise HTTPException(409, 'Wpis został zmieniony. Odśwież listę.')
            con.execute('UPDATE dictionary_entries SET values_json=?,version=version+1,updated_at=? WHERE id=?', (values(body, row), now(), entry_id))
            return entry(con.execute('SELECT * FROM dictionary_entries WHERE id=?', (entry_id,)).fetchone())

    @app.delete('/api/dictionaries/{identifier}/entries/{entry_id}', status_code=204)
    def delete_entry(identifier: str, entry_id: str, current=Depends(user)):
        with db() as con:
            owned(con, identifier, current)
            result = con.execute('DELETE FROM dictionary_entries WHERE id=? AND dictionary_id=?', (entry_id, identifier))
            if not result.rowcount: raise HTTPException(404, 'Nie znaleziono wpisu.')
        return Response(status_code=204)
