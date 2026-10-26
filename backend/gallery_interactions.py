"""Owner captions and visitor reactions scoped to a particular external link."""
import hashlib
import re
import secrets
import time

from fastapi import Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from backend import audit

SCHEMA = '''
CREATE TABLE IF NOT EXISTS photo_captions(
 document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS photo_likes(
 link_id TEXT NOT NULL REFERENCES external_links(id) ON DELETE CASCADE,
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 visitor_hash TEXT NOT NULL, PRIMARY KEY(link_id,document_id,visitor_hash));
CREATE TABLE IF NOT EXISTS photo_comments(
 id TEXT PRIMARY KEY,link_id TEXT NOT NULL REFERENCES external_links(id) ON DELETE CASCADE,
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 visitor_hash TEXT NOT NULL,author TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL,created_ts DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS photo_comment_page ON photo_comments(link_id,document_id,created_ts DESC,id DESC);
CREATE INDEX IF NOT EXISTS photo_comment_rate ON photo_comments(link_id,visitor_hash,created_ts);
'''
COOKIE = 'gallery_visitor'


class Caption(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=500)
    version: int = Field(ge=0)

    @field_validator('title')
    @classmethod
    def name(cls, value):
        value = ' '.join(value.split())
        if not value: raise ValueError('Podaj nazwę zdjęcia.')
        return value


class Like(BaseModel):
    liked: bool


class Comment(BaseModel):
    author: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=1000)

    @field_validator('author', 'content')
    @classmethod
    def nonempty(cls, value):
        value = value.strip()
        if not value: raise ValueError('Uzupełnij nazwę i treść komentarza.')
        return value


def visitor(request, response):
    token = request.cookies.get(COOKIE, '')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{40,90}', token):
        token = secrets.token_urlsafe(32)
        response.set_cookie(COOKIE, token, max_age=180 * 86400, httponly=True, samesite='lax',
                            secure=request.url.hostname not in ('127.0.0.1', 'localhost', 'testserver'))
    return hashlib.sha256(token.encode()).hexdigest()


def counts(con, link_id, document_id):
    return {'likes_count': con.execute('SELECT count(*) FROM photo_likes WHERE link_id=? AND document_id=?', (link_id, document_id)).fetchone()[0],
            'comments_count': con.execute('SELECT count(*) FROM photo_comments WHERE link_id=? AND document_id=?', (link_id, document_id)).fetchone()[0]}


def decorate(con, row, link, data):
    caption = con.execute('SELECT * FROM photo_captions WHERE document_id=?', (row['id'],)).fetchone()
    data.update(description=caption['description'] if caption else '', caption_version=caption['version'] if caption else 0)
    if caption: data['title'] = caption['title']
    if link: data.update(counts(con, link['id'], row['id']))
    return data


def install(app, db, user, now, public_document, resolve, can_manage, is_image, public_info):
    def photo(con, token, document_id):
        row = public_document(con, token, document_id)
        if not is_image(row): raise HTTPException(422, 'Ta funkcja jest dostępna dla zdjęć.')
        link, *_ = resolve(con, token, with_scope=False)
        return row, link

    @app.get('/api/public-shares/{token}/permissions')
    def permissions(token: str, current=Depends(user)):
        with db() as con:
            link, root, *_ = resolve(con, token, with_scope=False)
            return {'can_edit': can_manage(con, current, root, 'folder' if link['folder_id'] else 'document')}

    @app.patch('/api/public-shares/{token}/documents/{document_id}/caption')
    def caption(token: str, document_id: str, body: Caption, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row, link = photo(con, token, document_id)
            if not can_manage(con, current, row, 'document'): raise HTTPException(403, 'Nazwę i opis może zmieniać tylko właściciel zdjęcia.')
            previous = con.execute('SELECT * FROM photo_captions WHERE document_id=?', (document_id,)).fetchone()
            version = previous['version'] if previous else 0
            if version != body.version: raise HTTPException(409, 'Nazwa lub opis zmieniły się. Odśwież galerię przed zapisem.')
            con.execute('''INSERT INTO photo_captions(document_id,title,description,version) VALUES(?,?,?,?)
                ON CONFLICT(document_id) DO UPDATE SET title=excluded.title,description=excluded.description,version=excluded.version''',
                (document_id, body.title, body.description.strip(), version + 1))
            audit.record(con, current, 'document', row, 'Zmieniono nazwę i opis zdjęcia', [
                audit.change('title', previous['title'] if previous else row['title'], body.title),
                audit.change('description', previous['description'] if previous else '', body.description.strip())])
            return public_info(row, con, link)

    def comment_info(row, identity):
        return {key: row[key] for key in ('id', 'author', 'content', 'created_at')} | {'mine': row['visitor_hash'] == identity}

    def activity(con, link_id, document_id, identity, offset=0):
        total = counts(con, link_id, document_id)
        rows = con.execute('''SELECT * FROM photo_comments WHERE link_id=? AND document_id=?
            ORDER BY created_ts DESC,id DESC LIMIT 50 OFFSET ?''', (link_id, document_id, offset)).fetchall()
        return total | {'liked': bool(con.execute('SELECT 1 FROM photo_likes WHERE link_id=? AND document_id=? AND visitor_hash=?',
                       (link_id, document_id, identity)).fetchone()), 'comments': [comment_info(row, identity) for row in reversed(rows)],
                       'has_more': offset + len(rows) < total['comments_count']}

    @app.get('/api/public-shares/{token}/documents/{document_id}/activity')
    def read_activity(token: str, document_id: str, request: Request, response: Response, offset: int = Query(0, ge=0, le=100000)):
        with db() as con:
            _, link = photo(con, token, document_id)
            return activity(con, link['id'], document_id, visitor(request, response), offset)

    @app.put('/api/public-shares/{token}/documents/{document_id}/like')
    def like(token: str, document_id: str, body: Like, request: Request, response: Response):
        with db() as con:
            con.begin_write()
            _, link = photo(con, token, document_id)
            identity = visitor(request, response)
            if body.liked:
                con.execute('INSERT INTO photo_likes(link_id,document_id,visitor_hash) VALUES(?,?,?) ON CONFLICT DO NOTHING', (link['id'], document_id, identity))
            else: con.execute('DELETE FROM photo_likes WHERE link_id=? AND document_id=? AND visitor_hash=?', (link['id'], document_id, identity))
            return counts(con, link['id'], document_id) | {'liked': body.liked}

    @app.post('/api/public-shares/{token}/documents/{document_id}/comments', status_code=201)
    def comment(token: str, document_id: str, body: Comment, request: Request, response: Response):
        with db() as con:
            con.begin_write()
            _, link = photo(con, token, document_id)
            identity = visitor(request, response)
            stamp = time.time()
            recent = con.execute('SELECT count(*) FROM photo_comments WHERE link_id=? AND visitor_hash=? AND created_ts>?', (link['id'], identity, stamp - 60)).fetchone()[0]
            if recent >= 10: raise HTTPException(429, 'Dodano zbyt wiele komentarzy. Odczekaj minutę.')
            identifier = secrets.token_hex(16)
            con.execute('INSERT INTO photo_comments(id,link_id,document_id,visitor_hash,author,content,created_at,created_ts) VALUES(?,?,?,?,?,?,?,?)',
                        (identifier, link['id'], document_id, identity, body.author, body.content, now(), stamp))
            return comment_info(con.execute('SELECT * FROM photo_comments WHERE id=?', (identifier,)).fetchone(), identity)

    @app.delete('/api/public-shares/{token}/documents/{document_id}/comments/{comment_id}', status_code=204)
    def delete_own_comment(token: str, document_id: str, comment_id: str, request: Request, response: Response):
        with db() as con:
            con.begin_write()
            _, link = photo(con, token, document_id)
            identity = visitor(request, response)
            if not con.execute('DELETE FROM photo_comments WHERE id=? AND link_id=? AND document_id=? AND visitor_hash=?',
                               (comment_id, link['id'], document_id, identity)).rowcount:
                raise HTTPException(404, 'Nie znaleziono Twojego komentarza.')

    @app.delete('/api/gallery-comments/{comment_id}', status_code=204)
    def moderate(comment_id: str, current=Depends(user)):
        with db() as con:
            con.begin_write()
            comment = con.execute('''SELECT c.* FROM photo_comments c JOIN external_links l ON l.id=c.link_id
                WHERE c.id=? AND l.user_id=?''', (comment_id, current['id'])).fetchone()
            if not comment: raise HTTPException(404, 'Nie znaleziono komentarza.')
            row = con.execute('SELECT * FROM documents WHERE id=?', (comment['document_id'],)).fetchone()
            if not row or not can_manage(con, current, row, 'document'): raise HTTPException(403, 'Brak uprawnień do moderowania komentarzy.')
            con.execute('DELETE FROM photo_comments WHERE id=?', (comment_id,))
