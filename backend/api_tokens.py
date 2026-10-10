"""Revocable personal API keys; only hashed keys are stored."""
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Literal
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

SCHEMA = '''
CREATE TABLE IF NOT EXISTS api_access_tokens(
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 name TEXT NOT NULL,token_hash TEXT NOT NULL UNIQUE,scope TEXT NOT NULL,
 created_at TEXT NOT NULL,expires REAL NOT NULL);
CREATE INDEX IF NOT EXISTS api_token_owner ON api_access_tokens(user_id);
'''

class TokenInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scope: Literal['read', 'write'] = 'read'
    expires_days: int = Field(default=90, ge=1, le=365)

class TokenInfo(BaseModel):
    id: str
    name: str
    scope: Literal['read', 'write']
    expires: float

class TokenCreated(TokenInfo):
    token: str

class TokenListed(TokenInfo):
    created_at: str

def install(app, db, user):
    def session_user(request: Request, current=Depends(user)):
        if getattr(request.state, 'api_token', False):
            raise HTTPException(403, 'Kluczami API zarządzaj po zalogowaniu w przeglądarce.')
        return current

    @app.get('/api/access-tokens', response_model=list[TokenListed], tags=['Integracje API'])
    def list_tokens(current=Depends(session_user)):
        with db() as con:
            return [dict(row) for row in con.execute('SELECT id,name,scope,created_at,expires FROM api_access_tokens WHERE user_id=? ORDER BY created_at DESC,id', (current['id'],))]

    @app.post('/api/access-tokens', status_code=201, response_model=TokenCreated, tags=['Integracje API'])
    def create_token(body: TokenInput, current=Depends(session_user)):
        name = body.name.strip()
        if not name: raise HTTPException(422, 'Podaj nazwę klucza API.')
        now = datetime.now(timezone.utc)
        identifier, token = secrets.token_hex(16), 'edoc_' + secrets.token_urlsafe(32)
        expires = now.timestamp() + body.expires_days * 86400
        with db() as con:
            con.begin_write()
            if con.execute('SELECT count(*) FROM api_access_tokens WHERE user_id=? AND expires>?', (current['id'], now.timestamp())).fetchone()[0] >= 20:
                raise HTTPException(409, 'Możesz mieć maksymalnie 20 aktywnych kluczy API.')
            con.execute('INSERT INTO api_access_tokens VALUES(?,?,?,?,?,?,?)',
                (identifier, current['id'], name, hashlib.sha256(token.encode()).hexdigest(), body.scope, now.isoformat(), expires))
        return {'id': identifier, 'name': name, 'scope': body.scope, 'expires': expires, 'token': token}

    @app.delete('/api/access-tokens/{identifier}', status_code=204, tags=['Integracje API'])
    def revoke_token(identifier: str, current=Depends(session_user)):
        with db() as con:
            if not con.execute('DELETE FROM api_access_tokens WHERE id=? AND user_id=?', (identifier, current['id'])).rowcount:
                raise HTTPException(404, 'Nie znaleziono klucza API.')
