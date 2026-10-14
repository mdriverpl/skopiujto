"""Resource permissions, combined from account rights and group grants."""
from fastapi import HTTPException
from pathlib import Path

ACTIONS = ('read', 'edit', 'add', 'delete')
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.heic', '.bmp', '.avif', '.ico', '.tif', '.tiff'}

def permissions(con, current, folder_id, owner_id=None):
    scopes = []
    resource_owner = owner_id
    own = owner_id == current['id'] or (folder_id is None and owner_id is None)
    visited = set()
    while folder_id is not None and folder_id not in visited:
        visited.add(folder_id)
        scopes.append(folder_id)
        folder = con.execute('SELECT user_id,parent_id,access_mode FROM folders WHERE id=?', (folder_id,)).fetchone()
        if not folder:
            break
        if resource_owner is None:
            resource_owner = folder['user_id']
        own = own or folder['user_id'] == current['id']
        if folder['access_mode'] != 'inherit':
            break
        folder_id = folder['parent_id']
    else:
        scopes.append('root')
    result = {action: bool(current.get('can_' + action, False)) if own else False for action in ACTIONS}
    placeholders = ','.join('?' for _ in scopes)
    owner = con.execute('SELECT company_id FROM users WHERE id=?', (resource_owner or current['id'],)).fetchone()
    company_id = owner['company_id'] if owner else current.get('company_id')
    rows = list(con.execute(f'''SELECT p.can_read,p.can_edit,p.can_add,p.can_delete FROM group_permissions p
      JOIN group_members m ON m.group_id=p.group_id
      JOIN groups g ON g.id=p.group_id
      WHERE m.user_id=? AND g.company_id=? AND p.scope IN ({placeholders})''', (current['id'], company_id, *scopes)))
    rows += list(con.execute(f'''SELECT can_read,can_edit,can_add,can_delete FROM folder_user_permissions
      WHERE user_id=? AND folder_id IN ({placeholders})''', (current['id'], *scopes)))
    for row in rows:
        for action in ACTIONS:
            result[action] = result[action] or bool(row['can_' + action])
    return result

def require(rights, action):
    if not rights[action]:
        raise HTTPException(403, 'Brak uprawnienia: ' + {'read': 'odczyt', 'edit': 'edycja', 'add': 'dodawanie', 'delete': 'usuwanie', 'send': 'wysyłanie pliku', 'workflow': 'zmiana statusu dokumentu'}[action] + '.')

def document_permissions(con, current, row):
    rights = permissions(con, current, row['folder_id'], row['user_id'])
    rights['workflow'] = bool(rights['read'] and rights['edit'] and row['user_id'] == current['id'] and
                              (not row['filename'] or (row['uploaded_by'] or row['user_id']) == current['id']))
    rights['send'] = bool(row['filename'] and rights['read'] and rights['edit'] and
                         row['user_id'] == current['id'] and (row['uploaded_by'] or row['user_id']) == current['id'])
    # Group grants and the admin role never allow editing another author's document.
    if row['user_id'] != current['id']:
        rights['edit'] = False
    if row['filename'] and Path(row['filename']).suffix.lower() in IMAGE_EXTENSIONS:
        rights['edit'] = False
    # A file can only be deleted or replaced by its uploader, even by an admin.
    uploader = row['uploaded_by'] or row['user_id']
    if row['filename'] and uploader != current['id']:
        rights['delete'] = False
    return rights
