"""Validated photo contributions to explicitly enabled external folder links."""
import secrets
import time
from pathlib import Path

from fastapi import Depends, File, Form, HTTPException, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool
from backend import access, audit, gallery_interactions, images, storage

MAX_UPLOAD = 10 * 1024 * 1024
FORMATS = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP', '.gif': 'GIF',
           '.bmp': 'BMP', '.avif': 'AVIF', '.ico': 'ICO'}
SCHEMA = '''
ALTER TABLE external_links ADD COLUMN IF NOT EXISTS allow_uploads INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS gallery_uploads(
 id TEXT PRIMARY KEY,link_id TEXT NOT NULL REFERENCES external_links(id) ON DELETE CASCADE,
 document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,visitor_hash TEXT NOT NULL,created_ts DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS gallery_upload_rate ON gallery_uploads(link_id,created_ts,visitor_hash);
'''


def validate_photo(data, filename):
    filename = Path((filename or '').replace('\\', '/')).name
    if len(filename) > 255 or any(ord(char) < 32 for char in filename):
        raise HTTPException(422, 'Nazwa pliku jest zbyt długa lub zawiera niedozwolone znaki.')
    expected = FORMATS.get(Path(filename).suffix.lower())
    if not expected: raise HTTPException(415, 'Wybierz zdjęcie JPG, PNG, WebP, GIF, BMP, AVIF lub ICO.')
    if len(data) > MAX_UPLOAD: raise HTTPException(413, 'Maksymalny rozmiar zdjęcia to 10 MB.')
    try:
        with images.open_image(data) as image:
            if image.format != expected: raise HTTPException(415, 'Zawartość pliku nie odpowiada formatowi zdjęcia.')
            image.verify()
    except (OSError, ValueError, SyntaxError, EOFError):
        raise HTTPException(415, 'Nie można odczytać tego zdjęcia.') from None
    return filename


def install(app, db, user, now, resolve, can_manage, public_info):
    def target(con, token, folder_id, current):
        link, root, folders, _, owner = resolve(con, token)
        if not link['folder_id']: raise HTTPException(422, 'Zdjęcia można dodawać do udostępnionego katalogu.')
        if current is None:
            if not link['allow_uploads']: raise HTTPException(403, 'Właściciel nie zezwolił na dodawanie zdjęć przez ten link.')
        elif not can_manage(con, current, root, 'folder'):
            raise HTTPException(403, 'Tylko właściciel może dodawać zdjęcia w tym trybie.')
        selected = folder_id or root['id']
        if selected not in folders: raise HTTPException(404, 'Katalog nie jest objęty tym linkiem.')
        if not access.permissions(con, owner, selected, owner['id'])['add']:
            raise HTTPException(403, 'Nie można dodawać zdjęć do tego katalogu.')
        return link, owner, selected

    def quota(con, link, identity):
        stamp = time.time()
        recent = con.execute('SELECT count(*) FROM gallery_uploads WHERE link_id=? AND visitor_hash=? AND created_ts>?',
                             (link['id'], identity, stamp - 3600)).fetchone()[0]
        total = con.execute('SELECT count(*) FROM gallery_uploads WHERE link_id=? AND created_ts>?',
                            (link['id'], stamp - 86400)).fetchone()[0]
        if recent >= 20: raise HTTPException(429, 'Możesz dodać do 20 zdjęć w ciągu godziny. Spróbuj później.')
        if total >= 100: raise HTTPException(429, 'Osiągnięto dzienny limit 100 zdjęć dodanych przez odbiorców tego linku.')

    async def save(token, folder_id, file, request, response, current=None):
        identity = gallery_interactions.visitor(request, response)
        with db() as con:
            link, owner, selected = target(con, token, folder_id, current)
            if current is None: quota(con, link, identity)
        try: data = await file.read(MAX_UPLOAD + 1)
        finally: await file.close()
        filename = await run_in_threadpool(validate_photo, data, file.filename)
        bucket, key = await run_in_threadpool(storage.put, data, owner['id'])
        identifier = secrets.token_hex(16)
        stamp = now()
        try:
            with db() as con:
                con.begin_write()
                # Permissions, destination and quotas may change during remote storage I/O.
                link, owner, selected = target(con, token, folder_id, current)
                if current is None: quota(con, link, identity)
                con.execute('''INSERT INTO documents(id,user_id,title,category,content,status,created_at,updated_at,
                    filename,file,object_bucket,object_key,file_size,folder_id,uploaded_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (identifier, owner['id'], filename[:200], 'Pliki', '', 'Gotowy', stamp, stamp, filename,
                     None if key else data, bucket, key, len(data), selected, owner['id']))
                if current is None:
                    con.execute('INSERT INTO gallery_uploads(id,link_id,document_id,visitor_hash,created_ts) VALUES(?,?,?,?,?)',
                                (secrets.token_hex(16), link['id'], identifier, identity, time.time()))
                row = con.execute('SELECT * FROM documents WHERE id=?', (identifier,)).fetchone()
                actor = current or {'id': 'external-link:' + link['id'], 'name': 'Odbiorca linku (bez logowania)'}
                audit.record(con, actor, 'document', row, 'Dodano zdjęcie do galerii', [audit.change('filename', None, filename)])
                return public_info(row, con, link)
        except Exception:
            await run_in_threadpool(storage.cleanup, bucket, key)
            raise

    @app.post('/api/public-shares/{token}/photos', status_code=201)
    async def contribute(token: str, request: Request, response: Response, file: UploadFile = File(...),
                         folder_id: str | None = Form(None, max_length=64)):
        return await save(token, folder_id, file, request, response)

    @app.post('/api/public-shares/{token}/owner-photos', status_code=201)
    async def owner_upload(token: str, request: Request, response: Response, file: UploadFile = File(...),
                           folder_id: str | None = Form(None, max_length=64), current=Depends(user)):
        return await save(token, folder_id, file, request, response, current)
