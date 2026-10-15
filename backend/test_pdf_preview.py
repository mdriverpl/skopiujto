import io
from botocore.response import StreamingBody
from backend.test_storage import app_client, s3, put_params
from backend.test_access import READER, create_reader, login

PDF = b'%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF'


def test_pdf_preview_is_inline_private_and_download_stays_attachment(app_client):
    _, client = app_client
    reader = create_reader(client)
    response = client.post('/api/files', files={'file': ('Test.PDF', PDF)})
    assert response.status_code == 201
    identifier = response.json()['id']
    response = client.get(f'/api/documents/{identifier}/preview')
    assert response.status_code == 200 and response.content == PDF
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['content-disposition'].startswith('inline;')
    assert response.headers['cache-control'] == 'no-store'
    assert client.get(f'/api/documents/{identifier}/file').headers['content-disposition'].startswith('attachment;')
    login(client, READER)
    assert client.get(f'/api/documents/{identifier}/preview').status_code == 404
    client.post('/api/logout')
    assert client.get(f'/api/documents/{identifier}/preview').status_code == 401


def test_pdf_preview_streams_from_portal_storage(s3):
    main, client, stub = s3
    stub.add_response('put_object', {}, put_params(PDF))
    doc = client.post('/api/files', files={'file': ('umowa.pdf', PDF)}).json()
    with main.db() as con:
        row = con.execute('SELECT object_bucket,object_key FROM documents WHERE id=?', (doc['id'],)).fetchone()
    stub.add_response('get_object', {'Body': StreamingBody(io.BytesIO(PDF), len(PDF))},
                      {'Bucket': row['object_bucket'], 'Key': row['object_key']})
    result = client.get(f"/api/documents/{doc['id']}/preview")
    assert result.status_code == 200 and result.content == PDF
    assert result.headers['content-type'] == 'application/pdf'
