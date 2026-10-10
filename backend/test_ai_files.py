import base64
import io
import json
import zipfile

import pytest
from PIL import Image

from backend import ai_files
from backend.test_storage import app_client
from backend.test_ai import provider
from backend.test_access import READER, create_reader, login


def office_file(path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr(path, '<document>Umowa sprzedaży</document>')
    return stream.getvalue()


@pytest.mark.parametrize('name, data, mime', [
    ('umowa.pdf', b'%PDF-1.7\nmock PDF content', 'application/pdf'),
    ('umowa.docx', office_file('word/document.xml'), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    ('umowa.odt', office_file('content.xml'), 'application/vnd.oasis.opendocument.text'),
    ('umowa.doc', bytes.fromhex('D0CF11E0A1B11AE1') + b'mock Word content', 'application/msword'),
    ('umowa.rtf', b'{\\rtf1 mock contract}', 'application/rtf'),
    ('umowa.txt', 'Umowa sprzedaży'.encode('utf-8'), 'text/plain'),
    ('umowa.md', b'# Contract\nText', 'text/markdown'),
])
def test_file_content_reaches_provider_without_storing_source_or_template(app_client, provider, name, data, mime):
    _, client = app_client
    calls, _ = provider
    before = client.get('/api/templates').json()
    response = client.post('/api/ai/templates/from-file', files={'file': (name, data, 'application/octet-stream')},
                           data={'prompt': 'Zamień dane stron na pola do uzupełnienia.'})
    assert response.status_code == 200, response.text
    assert response.json()['rich_content']['type'] == 'doc'
    assert client.get('/api/templates').json() == before and client.get('/api/documents').json() == []
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    assert payload['store'] is False
    content = payload['input'][0]['content']
    assert content[0]['type'] == 'input_file' and content[0]['filename'] == name
    assert content[0]['file_data'].startswith(f'data:{mime};base64,')
    assert base64.b64decode(content[0]['file_data'].split(',', 1)[1]) == data
    assert content[1]['text'] == 'Zamień dane stron na pola do uzupełnienia.'
    assert 'materiałem źródłowym' in payload['instructions']


@pytest.mark.parametrize('extension, format', [('png', 'PNG'), ('jpg', 'JPEG'), ('webp', 'WEBP')])
def test_scan_uses_image_input_and_default_prompt(app_client, provider, extension, format):
    _, client = app_client
    calls, _ = provider
    stream = io.BytesIO()
    Image.new('RGB', (20, 20), 'white').save(stream, format=format)
    data = stream.getvalue()
    response = client.post('/api/ai/templates/from-file', files={'file': (f'scan.{extension}', data)})
    assert response.status_code == 200
    content = json.loads(calls[0].content)['input'][0]['content']
    assert content[0]['type'] == 'input_image'
    assert base64.b64decode(content[0]['image_url'].split(',', 1)[1]) == data
    assert 'załączonego dokumentu' in content[1]['text']


@pytest.mark.parametrize('name, data, expected', [
    ('app.exe', b'MZexecutable', 415), ('blank.txt', b'', 422),
    ('wrong.pdf', b'not a PDF', 422), ('wrong.docx', b'not a zip', 422),
    ('wrong.odt', office_file('unexpected.xml'), 422), ('wrong.doc', b'not Word', 422),
    ('wrong.rtf', b'plain text', 422), ('binary.txt', b'abc\x00\x01', 422),
    ('wrong.png', b'not image', 415),
])
def test_rejects_unusable_sources_before_calling_openai(app_client, provider, name, data, expected):
    main, client = app_client
    calls, _ = provider
    response = client.post('/api/ai/templates/from-file', files={'file': (name, data)})
    assert response.status_code == expected
    assert not calls and not main.ai_requests


def test_size_permissions_and_prompt_limits(app_client, provider, monkeypatch):
    main, client = app_client
    calls, _ = provider
    monkeypatch.setattr(ai_files, 'MAX_BYTES', 64)
    assert client.post('/api/ai/templates/from-file', files={'file': ('large.txt', b'x' * 65)}).status_code == 413
    assert client.post('/api/ai/templates/from-file', files={'file': ('source.txt', b'Contract')},
                       data={'prompt': 'x' * 8001}).status_code == 422
    create_reader(client)
    login(client, READER)
    assert client.post('/api/ai/templates/from-file', files={'file': ('source.txt', b'Contract')}).status_code == 403
    client.post('/api/logout')
    assert client.post('/api/ai/templates/from-file', files={'file': ('source.txt', b'Contract')}).status_code == 401
    assert not calls and not main.ai_requests


def test_provider_failure_releases_busy_state_and_allows_retry(app_client, provider):
    main, client = app_client
    calls, result = provider
    result['status'] = 429
    assert client.post('/api/ai/templates/from-file', files={'file': ('source.txt', b'Contract')}).status_code == 503
    assert not main.ai_requests
    result['status'] = 200
    assert client.post('/api/ai/templates/from-file', files={'file': ('source.txt', b'Contract')}).status_code == 200
    assert len(calls) == 2


def test_filename_is_sanitized_and_text_encodings_are_normalized():
    part = ai_files.attachment('C:\\secret\\umowa.TXT', 'Umowa sprzedaży'.encode('cp1250'))
    assert part['filename'] == 'umowa.txt'
    assert base64.b64decode(part['file_data'].split(',', 1)[1]).decode('utf-8') == 'Umowa sprzedaży'
    utf16 = ai_files.attachment('contract.txt', 'Umowa sprzedaży'.encode('utf-16'))
    assert base64.b64decode(utf16['file_data'].split(',', 1)[1]).decode('utf-8') == 'Umowa sprzedaży'
