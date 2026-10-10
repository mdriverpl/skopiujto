"""Validate bounded user-selected attachments for model file/image input."""
import base64
import io
import zipfile
from pathlib import Path

from fastapi import HTTPException
from backend import images

MAX_BYTES = 10 * 1024 * 1024
MIME_TYPES = {'.pdf': 'application/pdf', '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.odt': 'application/vnd.oasis.opendocument.text', '.rtf': 'application/rtf',
    '.txt': 'text/plain', '.md': 'text/markdown', '.png': 'image/png',
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}


def attachment(filename, data):
    name = Path((filename or '').replace('\\', '/')).name
    extension = Path(name).suffix.lower()
    if extension not in MIME_TYPES:
        raise HTTPException(415, 'Wybierz PDF, DOC/DOCX, ODT, RTF, TXT/MD albo skan PNG/JPG/WEBP.')
    if len(data) > MAX_BYTES:
        raise HTTPException(413, 'Maksymalny rozmiar pliku do AI to 10 MB.')
    if not data:
        raise HTTPException(422, 'Wybrany plik jest pusty.')
    def invalid():
        raise HTTPException(422, 'Nie można odczytać pliku lub jego zawartość nie odpowiada rozszerzeniu.')
    if extension in ('.png', '.jpg', '.jpeg', '.webp'):
        image = images.open_image(data)
        try:
            expected = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.webp': 'WEBP'}[extension]
            if image.format != expected: invalid()
            try: image.verify()
            except (OSError, ValueError, SyntaxError): invalid()
        finally:
            image.close()
        return {'type': 'input_image', 'image_url': f"data:{MIME_TYPES[extension]};base64,{base64.b64encode(data).decode('ascii')}"}
    if extension == '.pdf' and not data.lstrip().startswith(b'%PDF-'): invalid()
    if extension == '.doc' and not data.startswith(bytes.fromhex('D0CF11E0A1B11AE1')): invalid()
    if extension == '.rtf' and not data.lstrip().startswith(b'{\\rtf'): invalid()
    if extension in ('.docx', '.odt'):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                required = 'word/document.xml' if extension == '.docx' else 'content.xml'
                if len(archive.infolist()) > 10000 or required not in archive.namelist(): invalid()
        except (zipfile.BadZipFile, ValueError):
            invalid()
    if extension in ('.txt', '.md'):
        try:
            text = data.decode('utf-16') if data.startswith((b'\xff\xfe', b'\xfe\xff')) else data.decode('utf-8-sig')
        except UnicodeDecodeError:
            try: text = data.decode('cp1250')
            except UnicodeDecodeError: invalid()
        if not text.strip() or any(ord(char) < 32 and char not in '\t\r\n' for char in text): invalid()
        data = text.encode('utf-8')
    safe_name = Path(name).stem[:150] + extension
    return {'type': 'input_file', 'filename': safe_name,
            'file_data': f"data:{MIME_TYPES[extension]};base64,{base64.b64encode(data).decode('ascii')}"}
