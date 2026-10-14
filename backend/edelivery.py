"""Owner-private register of manually entered electronic deliveries."""
import secrets
from datetime import date
from typing import Literal
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

SCHEMA = '''
CREATE TABLE IF NOT EXISTS edelivery_records(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, correspondent TEXT NOT NULL, address TEXT NOT NULL,
 reference TEXT NOT NULL, direction TEXT NOT NULL, status TEXT NOT NULL,
 record_date TEXT NOT NULL, notes TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS edelivery_owner ON edelivery_records(user_id);
'''

class DeliveryInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    correspondent: str = Field(min_length=1, max_length=200)
    address: str = Field(default='', max_length=200)
    reference: str = Field(default='', max_length=200)
    direction: Literal['incoming', 'outgoing'] = 'incoming'
    status: Literal['registered', 'sent', 'delivered', 'received', 'failed'] = 'registered'
    record_date: date
    notes: str = Field(default='', max_length=20000)
    version: int | None = Field(default=None, ge=1)

    @field_validator('title', 'correspondent')
    @classmethod
    def required_text(cls, value):
        if not value.strip():
            raise ValueError('Podaj temat i nadawcę lub odbiorcę przesyłki.')
        return value.strip()

    @field_validator('address', 'reference')
    @classmethod
    def clean_text(cls, value):
        return value.strip()

def install(app, db, user, now):
    def owned(con, identifier, current):
        row = con.execute('SELECT * FROM edelivery_records WHERE id=? AND user_id=?', (identifier, current['id'])).fetchone()
        if not row:
            raise HTTPException(404, 'Nie znaleziono przesyłki.')
        return dict(row)

    def values(body):
        return (body.title, body.correspondent, body.address, body.reference, body.direction, body.status, body.record_date.isoformat(), body.notes)

    @app.get('/api/edeliveries')
    def listing(current=Depends(user)):
        with db() as con:
            records = []
            imports = {row['record_id']: dict(row) for row in con.execute('SELECT record_id,mailbox_address,message_id,remote_status,synced_at FROM edelivery_imports WHERE user_id=?', (current['id'],))}
            for row in con.execute('SELECT * FROM edelivery_records WHERE user_id=? ORDER BY record_date DESC,created_at DESC,id', (current['id'],)):
                item = dict(row)
                remote = imports.get(item['id'])
                if remote: item.update({key: value for key, value in remote.items() if key != 'record_id'})
                records.append(item)
            return records

    @app.post('/api/edeliveries', status_code=201)
    def create(body: DeliveryInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            identifier, timestamp = secrets.token_hex(16), now()
            con.execute('''INSERT INTO edelivery_records(
                id,user_id,title,correspondent,address,reference,direction,status,record_date,notes,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (identifier, current['id'], *values(body), timestamp, timestamp))
            return owned(con, identifier, current)

    @app.patch('/api/edeliveries/{identifier}')
    def update(identifier: str, body: DeliveryInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = owned(con, identifier, current)
            if con.execute('SELECT record_id FROM edelivery_imports WHERE record_id=?', (identifier,)).fetchone():
                raise HTTPException(409, 'Przesyłka pochodzi ze skrzynki. Jej dane aktualizuje synchronizacja.')
            if body.version != row['version']:
                raise HTTPException(409, 'Przesyłka została zmieniona. Odśwież rejestr i otwórz ją ponownie.')
            con.execute('''UPDATE edelivery_records SET title=?,correspondent=?,address=?,reference=?,
                direction=?,status=?,record_date=?,notes=?,updated_at=?,version=version+1 WHERE id=?''', (*values(body), now(), identifier))
            return owned(con, identifier, current)

    @app.delete('/api/edeliveries/{identifier}', status_code=204)
    def delete(identifier: str, current=Depends(user)):
        with db() as con:
            con.begin_write()
            owned(con, identifier, current)
            con.execute('DELETE FROM edelivery_records WHERE id=?', (identifier,))
        return Response(status_code=204)
