"""Personal notes, visible only to their owner."""
import secrets

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

SCHEMA = '''
CREATE TABLE IF NOT EXISTS notes(
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL, content TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS notes_owner ON notes(user_id);
'''


class NoteInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default='', max_length=20000)
    version: int | None = Field(default=None, ge=1)

    @field_validator('title')
    @classmethod
    def clean_title(cls, value):
        if not value.strip():
            raise ValueError('Podaj tytuł notatki.')
        return value.strip()


def install(app, db, user, now):
    def owned(con, identifier, current):
        row = con.execute('SELECT * FROM notes WHERE id=? AND user_id=?',
                          (identifier, current['id'])).fetchone()
        if not row:
            raise HTTPException(404, 'Nie znaleziono notatki.')
        return dict(row)

    @app.get('/api/notes')
    def listing(current=Depends(user)):
        with db() as con:
            return [dict(row) for row in con.execute(
                'SELECT * FROM notes WHERE user_id=? ORDER BY updated_at DESC,id', (current['id'],))]

    @app.post('/api/notes', status_code=201)
    def create(body: NoteInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            identifier, timestamp = secrets.token_hex(16), now()
            con.execute('INSERT INTO notes(id,user_id,title,content,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                        (identifier, current['id'], body.title, body.content, timestamp, timestamp))
            return owned(con, identifier, current)

    @app.patch('/api/notes/{identifier}')
    def update(identifier: str, body: NoteInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = owned(con, identifier, current)
            if body.version != row['version']:
                raise HTTPException(409, 'Notatka została zmieniona. Odśwież listę i otwórz ją ponownie.')
            con.execute('UPDATE notes SET title=?,content=?,updated_at=?,version=version+1 WHERE id=?',
                        (body.title, body.content, now(), identifier))
            return owned(con, identifier, current)

    @app.delete('/api/notes/{identifier}', status_code=204)
    def delete(identifier: str, current=Depends(user)):
        with db() as con:
            con.begin_write()
            owned(con, identifier, current)
            con.execute('DELETE FROM notes WHERE id=?', (identifier,))
        return Response(status_code=204)
