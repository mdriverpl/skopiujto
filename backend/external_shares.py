"""Revocable, owner-managed public links for files and folder trees."""
import hashlib
import secrets
import time
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from backend import access, audit, document_pdf, folder_archive, images, gallery_interactions, gallery_uploads

SCHEMA = '''
CREATE TABLE IF NOT EXISTS external_links(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
 folder_id TEXT REFERENCES folders(id) ON DELETE CASCADE,
 token_hash TEXT UNIQUE NOT NULL, view_mode TEXT NOT NULL,
 expires DOUBLE PRECISION NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
 CHECK((document_id IS NULL) != (folder_id IS NULL)));
CREATE INDEX IF NOT EXISTS external_link_owner ON external_links(user_id);
'''
SCHEMA += gallery_interactions.SCHEMA
SCHEMA += gallery_uploads.SCHEMA

Mode = Literal['catalog', 'gallery', 'tiles', 'preview']


class LinkInput(BaseModel):
    view_mode: Mode = 'catalog'
    hours: int = Field(default=168, ge=1, le=2160)
    allow_uploads: bool = False


class LinkView(BaseModel):
    view_mode: Mode | None = None
    allow_uploads: bool | None = None


def can_manage(con, current, row, kind):
    if current.get('impersonation', {}).get('read_only') or row['user_id'] != current['id']:
        return False
    if kind == 'document' and (row['uploaded_by'] or row['user_id']) != current['id']:
        return False
    rights = access.permissions(con, current, row['id'] if kind == 'folder' else row['folder_id'], row['user_id'])
    return rights['read'] and rights['edit']


def scope(con, root, current):
    """Only the sharer's own currently readable resources belong to a link."""
    all_folders = {row['id']: row for row in con.execute('SELECT * FROM folders WHERE user_id=? ORDER BY lower(name),id', (current['id'],))}
    children = {}
    for row in all_folders.values(): children.setdefault(row['parent_id'], []).append(row['id'])
    folders, queue = {}, [root['id']]
    while queue:
        identifier = queue.pop()
        if identifier in folders: continue
        row = all_folders.get(identifier)
        if not row or row['user_id'] != current['id'] or not access.permissions(con, current, identifier, row['user_id'])['read']:
            continue
        folders[identifier] = row
        queue.extend(children.get(identifier, []))
    files = {}
    for row in con.execute('''SELECT id,user_id,uploaded_by,folder_id,title,filename,version,coalesce(file_size,length(file)) AS file_size
        FROM documents WHERE user_id=? ORDER BY lower(title),id''', (current['id'],)):
        if row['folder_id'] in folders and can_manage(con, current, row, 'document'):
            files[row['id']] = row
    return folders, files


def info(row, con=None, link=None):
    suffix = Path(row['filename'] or '').suffix.lower()
    image = suffix in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.avif', '.ico'}
    result = {key: row[key] for key in ('id', 'title', 'filename', 'file_size', 'version')} | {
        'image': image, 'pdf': suffix == '.pdf', 'editor': not row['filename']}
    return gallery_interactions.decorate(con, row, link, result) if con is not None and image else result


def install(app, db, user, now, serialize_document, file_response, image_bytes):
    def resource(con, kind, identifier, current):
        table = 'folders' if kind == 'folder' else 'documents'
        row = con.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
        if not row or not can_manage(con, current, row, kind):
            raise HTTPException(404, 'Nie znaleziono zasobu do udostępnienia lub brak uprawnień.')
        return row

    def links(con, kind, identifier, current):
        resource(con, kind, identifier, current)
        field = 'folder_id' if kind == 'folder' else 'document_id'
        return [dict(row) for row in con.execute(f'''SELECT id,view_mode,expires,revoked,created_at,allow_uploads FROM external_links
            WHERE user_id=? AND {field}=? ORDER BY created_at DESC,id''', (current['id'], identifier))]

    @app.get('/api/external-links/{kind}/{identifier}')
    def listing(kind: Literal['folder', 'document'], identifier: str, current=Depends(user)):
        with db() as con: return links(con, kind, identifier, current)

    @app.post('/api/external-links/{kind}/{identifier}', status_code=201)
    def create(kind: Literal['folder', 'document'], identifier: str, body: LinkInput, current=Depends(user)):
        if kind == 'document' and body.allow_uploads: raise HTTPException(422, 'Dodawanie zdjęć wymaga linku do katalogu.')
        if kind == 'folder' and body.view_mode == 'preview':
            raise HTTPException(422, 'Dla katalogu wybierz katalog, galerię lub kafelki.')
        token = secrets.token_urlsafe(32)
        expires = time.time() + body.hours * 3600
        link_id = secrets.token_hex(16)
        with db() as con:
            con.begin_write()
            row = resource(con, kind, identifier, current)
            con.execute('''INSERT INTO external_links(id,user_id,document_id,folder_id,token_hash,view_mode,expires,created_at,allow_uploads)
                VALUES(?,?,?,?,?,?,?,?,?)''', (link_id, current['id'], identifier if kind == 'document' else None,
                identifier if kind == 'folder' else None, hashlib.sha256(token.encode()).hexdigest(), body.view_mode, expires, now(), body.allow_uploads))
            audit.record(con, current, kind, row, 'Utworzono zewnętrzny link', [audit.change('view_mode', None, body.view_mode)])
        return {'id': link_id, 'path': '/public-share/' + token, 'expires': expires, 'view_mode': body.view_mode, 'allow_uploads': body.allow_uploads}

    def owned_link(con, link_id, current):
        link = con.execute('SELECT * FROM external_links WHERE id=? AND user_id=?', (link_id, current['id'])).fetchone()
        if not link: raise HTTPException(404, 'Nie znaleziono linku.')
        kind = 'folder' if link['folder_id'] else 'document'
        row = resource(con, kind, link['folder_id'] or link['document_id'], current)
        return link, kind, row

    @app.patch('/api/external-links/{link_id}')
    def change_view(link_id: str, body: LinkView, current=Depends(user)):
        with db() as con:
            con.begin_write()
            link, kind, row = owned_link(con, link_id, current)
            if kind == 'document' and body.allow_uploads: raise HTTPException(422, 'Dodawanie zdjęć wymaga linku do katalogu.')
            if kind == 'folder' and body.view_mode == 'preview': raise HTTPException(422, 'Niepoprawny widok katalogu.')
            if link['revoked'] or link['expires'] <= time.time(): raise HTTPException(410, 'Link jest już nieaktywny.')
            mode = body.view_mode or link['view_mode']
            uploads = int(body.allow_uploads) if body.allow_uploads is not None else link['allow_uploads']
            con.execute('UPDATE external_links SET view_mode=?,allow_uploads=? WHERE id=?', (mode, uploads, link_id))
            changes = []
            if mode != link['view_mode']: changes.append(audit.change('view_mode', link['view_mode'], mode))
            if uploads != link['allow_uploads']: changes.append(audit.change('allow_uploads', bool(link['allow_uploads']), bool(uploads)))
            if changes: audit.record(con, current, kind, row, 'Zmieniono ustawienia linku', changes)
        return {'view_mode': mode, 'allow_uploads': bool(uploads)}

    @app.delete('/api/external-links/{link_id}', status_code=204)
    def revoke(link_id: str, current=Depends(user)):
        with db() as con:
            con.begin_write()
            link = con.execute('SELECT * FROM external_links WHERE id=? AND user_id=?', (link_id, current['id'])).fetchone()
            if not link: raise HTTPException(404, 'Nie znaleziono linku.')
            con.execute('UPDATE external_links SET revoked=1 WHERE id=?', (link_id,))
            if not link['revoked']:
                kind = 'folder' if link['folder_id'] else 'document'
                table = 'folders' if kind == 'folder' else 'documents'
                row = con.execute(f'SELECT * FROM {table} WHERE id=?', (link['folder_id'] or link['document_id'],)).fetchone()
                if row: audit.record(con, current, kind, row, 'Wyłączono zewnętrzny link')

    def resolve(con, token, with_scope=True):
        link = con.execute('SELECT * FROM external_links WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not link: raise HTTPException(404, 'Link nie istnieje.')
        if link['revoked'] or link['expires'] <= time.time(): raise HTTPException(410, 'Link wygasł lub został wyłączony.')
        owner = con.execute('SELECT * FROM users WHERE id=? AND active=1 AND deleted_at IS NULL', (link['user_id'],)).fetchone()
        if not owner: raise HTTPException(410, 'Udostępnienie jest już niedostępne.')
        kind = 'folder' if link['folder_id'] else 'document'
        root = resource(con, kind, link['folder_id'] or link['document_id'], owner)
        folders, files = scope(con, root, owner) if kind == 'folder' and with_scope else ({}, {root['id']: root})
        return link, root, folders, files, owner

    @app.get('/api/public-shares/{token}')
    def public_view(token: str, folder_id: str | None = Query(None, max_length=64)):
        with db() as con:
            link, root, folders, files, owner = resolve(con, token)
            result = {'view_mode': link['view_mode'], 'expires': link['expires']}
            if not link['folder_id']:
                item = info(root, con, link)
                return result | {'kind': 'document', 'title': item['title'], 'document': item}
            selected = folder_id or root['id']
            if selected not in folders: raise HTTPException(404, 'Katalog nie jest objęty tym linkiem.')
            breadcrumbs, current = [], selected
            while current in folders:
                item = folders[current]
                breadcrumbs.insert(0, {'id': current, 'name': item['name']})
                if current == root['id']: break
                current = item['parent_id']
            return result | {'kind': 'folder', 'title': root['name'], 'folder_id': selected, 'breadcrumbs': breadcrumbs,
                'allow_uploads': bool(link['allow_uploads']), 'link_id': link['id'],
                'can_add_photos': access.permissions(con, owner, selected, root['user_id'])['add'],
                'folders': [{'id': row['id'], 'name': row['name']} for row in folders.values() if row['parent_id'] == selected],
                'files': [info(row, con, link) for row in files.values() if row['folder_id'] == selected]}

    def public_document(con, token, document_id):
        link, _, _, _, owner = resolve(con, token, with_scope=False)
        if link['document_id'] and document_id != link['document_id']:
            raise HTTPException(404, 'Plik nie jest objęty tym linkiem.')
        row = con.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
        if not row or not can_manage(con, owner, row, 'document'):
            raise HTTPException(404, 'Plik nie jest już objęty tym linkiem.')
        if link['folder_id']:
            folder_id, visited = row['folder_id'], set()
            while folder_id is not None and folder_id not in visited:
                visited.add(folder_id)
                folder = con.execute('SELECT * FROM folders WHERE id=?', (folder_id,)).fetchone()
                if (not folder or folder['user_id'] != owner['id'] or
                        not access.permissions(con, owner, folder_id, folder['user_id'])['read']): break
                if folder_id == link['folder_id']: return row
                folder_id = folder['parent_id']
            raise HTTPException(404, 'Plik nie jest objęty tym katalogiem.')
        return row

    @app.get('/api/public-shares/{token}/documents/{document_id}')
    def detail(token: str, document_id: str):
        with db() as con:
            row = public_document(con, token, document_id)
            data = serialize_document(row)
            return info(row, con) | {key: data[key] for key in ('content', 'rich_content', 'category')}

    @app.get('/api/public-shares/{token}/documents/{document_id}/file')
    def download(token: str, document_id: str):
        with db() as con:
            row = public_document(con, token, document_id)
            if row['filename']: return file_response(row)
            return Response(document_pdf.render_pdf(serialize_document(row)), media_type='application/pdf', headers={
                'Content-Disposition': "attachment; filename*=UTF-8''" + quote(folder_archive.safe_name(row['title']) + '.pdf', safe='')})

    @app.get('/api/public-shares/{token}/documents/{document_id}/location')
    def photo_location(token: str, document_id: str):
        with db() as con:
            row = public_document(con, token, document_id)
            if not info(row)['image']: return {'location': None}
        try: location = images.gps_location(image_bytes(row))
        except HTTPException as exc:
            if exc.status_code != 415: raise
            location = None
        # A revoked link or replaced file must not expose metadata after remote I/O.
        with db() as con:
            latest = public_document(con, token, document_id)
            if latest['version'] != row['version']:
                raise HTTPException(409, 'Zdjęcie zmieniło się. Otwórz je ponownie.')
        return {'location': location}

    @app.get('/api/public-shares/{token}/documents/{document_id}/preview')
    def preview(token: str, document_id: str):
        with db() as con:
            row = public_document(con, token, document_id)
            if row['filename']: return file_response(row, preview=True)
            return Response(document_pdf.render_pdf(serialize_document(row)), media_type='application/pdf')

    gallery_interactions.install(app, db, user, now, public_document, resolve, can_manage,
                                 lambda row: info(row)['image'], info)
    gallery_uploads.install(app, db, user, now, resolve, can_manage, info)

    @app.get('/api/public-shares/{token}/archive')
    def archive(token: str):
        with db() as con:
            link, root, folders, files, owner = resolve(con, token)
            if not link['folder_id']: raise HTTPException(422, 'ZIP jest dostępny dla katalogu.')
            output = folder_archive.build(con, root, owner, serialize_document,
                                         allowed_folders=set(folders), allowed_documents=set(files))
        return StreamingResponse(folder_archive.chunks(output), media_type='application/zip', headers={
            'Content-Disposition': "attachment; filename*=UTF-8''" + quote(folder_archive.safe_name(root['name']) + '.zip', safe='')},
            background=BackgroundTask(output.close))
