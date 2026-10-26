"""Export readable folder contents, preserving hierarchy and editor PDFs."""
import re
import tempfile
import zipfile
from pathlib import PurePosixPath

from fastapi import HTTPException
from backend import access, storage
from backend.document_pdf import render_pdf


def safe_name(value):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', '_', value or '').strip().rstrip('.')[:180]
    if not name or name in ('.', '..'): name = 'katalog'
    if re.fullmatch(r'(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', name, re.I): name = '_' + name
    return name


def unique_name(name, used):
    candidate = name
    path = PurePosixPath(name)
    number = 2
    while candidate.casefold() in used:
        candidate = f'{path.stem} ({number}){path.suffix}'
        number += 1
    used.add(candidate.casefold())
    return candidate


def build(con, root, current, serialize_document, allowed_folders=None, allowed_documents=None):
    folders = {row['id']: row for row in con.execute('SELECT * FROM folders ORDER BY lower(name),id')}
    children = {}
    for folder in folders.values(): children.setdefault(folder['parent_id'], []).append(folder['id'])
    subtree, queue = {}, [(root['id'], None)]
    while queue:
        folder_id, parent = queue.pop()
        if folder_id in subtree or (allowed_folders is not None and folder_id not in allowed_folders): continue
        subtree[folder_id] = parent
        queue.extend((child, folder_id) for child in children.get(folder_id, []))
    visible = {root['id']}
    def include_ancestors(folder_id):
        while folder_id is not None and folder_id not in visible:
            visible.add(folder_id)
            folder_id = subtree[folder_id]
    for folder_id in subtree:
        folder = folders[folder_id]
        if access.permissions(con, current, folder_id, folder['user_id'])['read']:
            include_ancestors(folder_id)
    selected = []
    for row in con.execute('SELECT id,user_id,folder_id,filename,uploaded_by FROM documents ORDER BY id'):
        if (row['folder_id'] in subtree and (allowed_documents is None or row['id'] in allowed_documents)
                and access.document_permissions(con, current, row)['read']):
            selected.append(row)
            include_ancestors(row['folder_id'])
    paths, names = {}, {}
    # Insertion order is parent before child, even for deep folder trees.
    for folder_id, parent in subtree.items():
        if folder_id not in visible: continue
        name = unique_name(safe_name(folders[folder_id]['name']), names.setdefault(parent, set()))
        paths[folder_id] = (paths[parent] if parent is not None else '') + name + '/'
    output = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024, mode='w+b')
    try:
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for path in paths.values(): archive.writestr(path, b'')
            for candidate in selected:
                row = con.execute('SELECT * FROM documents WHERE id=?', (candidate['id'],)).fetchone()
                if not row or row['folder_id'] != candidate['folder_id'] or not access.document_permissions(con, current, row)['read']:
                    raise HTTPException(409, 'Zawartość katalogu zmieniła się. Pobierz go ponownie.')
                name = safe_name(row['filename']) if row['filename'] else safe_name(row['title']) + '.pdf'
                name = unique_name(name, names.setdefault(row['folder_id'], set()))
                path = paths[row['folder_id']] + name
                if not row['filename']:
                    archive.writestr(path, render_pdf(serialize_document(row)))
                elif row['object_key']:
                    body = storage.get(row['object_bucket'], row['object_key'])
                    try:
                        with archive.open(path, 'w', force_zip64=True) as target:
                            for chunk in body.iter_chunks(chunk_size=64 * 1024): target.write(chunk)
                    finally: body.close()
                elif row['file'] is not None:
                    archive.writestr(path, bytes(row['file']))
                else:
                    raise HTTPException(503, 'Jeden z plików w katalogu jest niedostępny. Spróbuj ponownie.')
        output.seek(0)
        return output
    except Exception:
        output.close()
        raise


def chunks(output):
    try:
        while chunk := output.read(64 * 1024): yield chunk
    finally: output.close()
