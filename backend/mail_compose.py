"""Outgoing attachments and optional password protected ZIP archives."""
import io
import secrets
import zipfile
from pathlib import PurePosixPath

import pyzipper
from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from backend import mail_attachments, mail_settings

MAX_TOTAL = 20 * 1024 * 1024
MAX_FILES = 50


def filename(value):
    name = PurePosixPath((value or '').replace('\\', '/')).name
    name = ''.join(c for c in name if ord(c) >= 32 and ord(c) != 127).strip()[:200]
    return name if name not in ('', '.', '..') else 'plik'


def archive_name(value):
    name = filename(value or 'zalaczniki.zip')
    return name if name.lower().endswith('.zip') else name + '.zip'


def encrypt_password(password):
    return mail_settings.cipher().encrypt(password.encode()).decode() if password else ''


def password(row):
    if 'zip_password' in row:
        return row['zip_password']
    token = row.get('zip_password_secret', '')
    if not token:
        return ''
    try:
        return mail_settings.cipher().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        raise HTTPException(503, 'Nie można odczytać hasła ZIP. Sprawdź klucz szyfrowania poczty.') from None


def validate(parts):
    if len(parts) > MAX_FILES or sum(len(data) for _, data in parts) > MAX_TOTAL:
        raise HTTPException(422, 'Dodaj maksymalnie 50 plików o łącznym rozmiarze do 20 MB.')


def originals(con, mail_id):
    parts = []
    for part in con.execute('SELECT * FROM client_mail_attachments WHERE mail_id=? ORDER BY id', (mail_id,)):
        if part['data'] is not None:
            data = bytes(part['data'])
        elif part['disk_key']:
            try: data = mail_attachments.disk_path(part['disk_key']).read_bytes()
            except OSError: raise HTTPException(503, 'Zapisany załącznik jest niedostępny.') from None
        else:
            raise HTTPException(409, 'Załącznik nie jest dostępny lokalnie. Dodaj plik ponownie.')
        parts.append((filename(part['name']), data))
    return parts


def zip_bytes(parts, secret=''):
    validate(parts)
    output = io.BytesIO()
    archive_type = pyzipper.AESZipFile if secret else zipfile.ZipFile
    with archive_type(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        if secret:
            archive.setpassword(secret.encode())
            archive.setencryption(pyzipper.WZ_AES, nbits=256)
        used = set()
        for original, data in parts:
            name = filename(original)
            path = PurePosixPath(name)
            index = 2
            while name.casefold() in used:
                name = f'{path.stem} ({index}){path.suffix}'
                index += 1
            used.add(name.casefold())
            archive.writestr(name, data)
    return output.getvalue()


def outgoing(con, row):
    parts = originals(con, row['id'])
    validate(parts)
    if row.get('zip_enabled') and parts:
        return [(archive_name(row['zip_name']), zip_bytes(parts, password(row)))]
    return parts


def store(con, mail_id, parts):
    for name, data in parts:
        con.execute('INSERT INTO client_mail_attachments(id,mail_id,name,size,data) VALUES(?,?,?,?,?)',
                    (secrets.token_hex(16), mail_id, name, len(data), data))
