"""Private, reusable field values; independent of document sharing permissions."""
import json
import secrets

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from backend.document_fields import key
from backend import ai_memory

SCHEMA = '''
CREATE TABLE IF NOT EXISTS saved_document_data(
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, fields TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS saved_data_owner ON saved_document_data(user_id);
CREATE TABLE IF NOT EXISTS saved_data_sources(
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, source_key TEXT NOT NULL,
  data_id TEXT NOT NULL REFERENCES saved_document_data(id) ON DELETE CASCADE,
  PRIMARY KEY(user_id,source_key));
CREATE TABLE IF NOT EXISTS saved_data_contexts(
  data_id TEXT PRIMARY KEY REFERENCES saved_document_data(id) ON DELETE CASCADE,
  context TEXT NOT NULL);
'''


class DataInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    fields: dict[str, str] = Field(min_length=1, max_length=200)
    version: int | None = Field(default=None, ge=1)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('Podaj nazwę zestawu.')
        return value.strip()

    @field_validator('fields')
    @classmethod
    def clean_fields(cls, values):
        result = {}
        for label, value in values.items():
            normalized = key(label)
            if not normalized or len(label) > 120 or any(c in label for c in '[]\r\n'):
                raise ValueError('Nieprawidłowa nazwa pola.')
            if len(value) > 2000:
                raise ValueError('Wartość pola jest za długa.')
            if normalized in result:
                raise ValueError('Powtarzająca się nazwa pola.')
            if value.strip():
                result[normalized] = value
        if not result:
            raise ValueError('Uzupełnij co najmniej jedno pole.')
        return result


def output(row):
    return {name: row[name] for name in ('id', 'name', 'version', 'updated_at')} | {
        'fields': json.loads(row['fields'])}


class RememberInput(DataInput):
    source_key: str = Field(min_length=1, max_length=100)
    context: str = Field(default='', max_length=40000)


def install(app, db, user, now):
    pending_matches = set()
    def owned(con, identifier, current):
        row = con.execute('SELECT * FROM saved_document_data WHERE id=? AND user_id=?',
                          (identifier, current['id'])).fetchone()
        if not row:
            raise HTTPException(404, 'Nie znaleziono zestawu danych.')
        return row

    @app.get('/api/saved-data')
    def listing(current=Depends(user)):
        with db() as con:
            return [output(row) for row in con.execute(
                'SELECT * FROM saved_document_data WHERE user_id=? ORDER BY lower(name),id',
                (current['id'],))]

    @app.post('/api/saved-data', status_code=201)
    def create(body: DataInput, current=Depends(user)):
        identifier = secrets.token_hex(16)
        with db() as con:
            con.execute('INSERT INTO saved_document_data(id,user_id,name,fields,updated_at) VALUES(?,?,?,?,?)',
                        (identifier, current['id'], body.name, json.dumps(body.fields, ensure_ascii=False), now()))
            return output(owned(con, identifier, current))

    @app.post('/api/saved-data/remember')
    def remember(body: RememberInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            existing = con.execute('SELECT data_id FROM saved_data_sources WHERE user_id=? AND source_key=?',
                                   (current['id'], body.source_key)).fetchone()
            identifier = existing['data_id'] if existing else secrets.token_hex(16)
            if existing:
                con.execute('UPDATE saved_document_data SET name=?,fields=?,version=version+1,updated_at=? WHERE id=?',
                            (body.name, json.dumps(body.fields, ensure_ascii=False), now(), identifier))
            else:
                con.execute('INSERT INTO saved_document_data(id,user_id,name,fields,updated_at) VALUES(?,?,?,?,?)',
                            (identifier, current['id'], body.name, json.dumps(body.fields, ensure_ascii=False), now()))
                con.execute('INSERT INTO saved_data_sources VALUES(?,?,?)', (current['id'], body.source_key, identifier))
            con.execute('INSERT INTO saved_data_contexts VALUES(?,?) ON CONFLICT(data_id) DO UPDATE SET context=excluded.context',
                        (identifier, body.context))
            return output(owned(con, identifier, current))

    @app.post('/api/saved-data/match')
    async def match(body: ai_memory.MatchInput, current=Depends(user)):
        if any(not key(label) or len(label) > 120 or any(c in label for c in '[]\r\n') for label in body.fields):
            raise HTTPException(422, 'Nieprawidłowe nazwy pól.')
        if any(len(label) > 120 or len(value) > 2000 for label, value in body.values.items()):
            raise HTTPException(422, 'Nieprawidłowe dane dokumentu.')
        empty = [label for label in body.fields if not body.values.get(key(label), '').strip()]
        if not empty: return {'matches': {}}
        with db() as con:
            rows = con.execute('''SELECT d.*,c.context FROM saved_document_data d
                LEFT JOIN saved_data_contexts c ON c.data_id=d.id
                WHERE d.user_id=? ORDER BY d.updated_at DESC,d.id''', (current['id'],)).fetchall()
        candidates = []
        for row in rows:
            for index, (label, value) in enumerate(json.loads(row['fields']).items()):
                candidates.append({'id': f"{row['id']}:{index}", 'name': row['name'], 'field': label,
                    'value': value, 'related_fields': json.loads(row['fields']), 'context': (row['context'] or '')[:12000]})
        if not candidates: return {'matches': {}}
        total_size = sum(len(row['fields']) + min(len(row['context'] or ''), 12000) for row in rows)
        if len(candidates) > 600 or total_size > 250000:
            raise HTTPException(413, 'Za dużo zapisanych danych do dopasowania. Uporządkuj dane w słowniku AI.')
        if current['id'] in pending_matches:
            raise HTTPException(429, 'AI dopasowuje już dane. Poczekaj chwilę.')
        pending_matches.add(current['id'])
        try:
            return {'matches': await ai_memory.match(body.model_copy(update={'fields': empty}), candidates)}
        finally:
            pending_matches.discard(current['id'])

    @app.put('/api/saved-data/{identifier}')
    def update(identifier: str, body: DataInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = owned(con, identifier, current)
            if body.version != row['version']:
                raise HTTPException(409, 'Zestaw został zmieniony. Odśwież listę i spróbuj ponownie.')
            con.execute('UPDATE saved_document_data SET name=?,fields=?,version=version+1,updated_at=? WHERE id=?',
                        (body.name, json.dumps(body.fields, ensure_ascii=False), now(), identifier))
            return output(owned(con, identifier, current))

    @app.delete('/api/saved-data/{identifier}', status_code=204)
    def delete(identifier: str, current=Depends(user)):
        with db() as con:
            owned(con, identifier, current)
            con.execute('DELETE FROM saved_document_data WHERE id=?', (identifier,))
        return Response(status_code=204)
