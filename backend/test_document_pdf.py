from io import BytesIO

from backend.document_pdf import render_pdf
from backend.test_storage import app_client


def test_pdf_exports_polish_text_and_escaped_rich_content():
    from pypdf import PdfReader
    data = render_pdf({'title': 'Umowa', 'rich_content': {'type': 'doc', 'content': [
        {'type': 'heading', 'attrs': {'level': 1}, 'content': [{'type': 'text', 'text': 'Zażółć gęślą jaźń'}]},
        {'type': 'paragraph', 'content': [{'type': 'text', 'text': '<test> & warunki', 'marks': [{'type': 'bold'}, {'type': 'textStyle', 'attrs': {'fontSize': '18px', 'color': '#336699'}}]}]},
        {'type': 'orderedList', 'attrs': {'start': 3}, 'content': [{'type': 'listItem', 'content': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Treść punktu'}]}]}]}
    ]}})
    assert data.startswith(b'%PDF-')
    text = ''.join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)
    assert 'Zażółć gęślą jaźń' in text
    assert '<test> & warunki' in text
    assert '3.' in text and 'Treść punktu' in text


def test_plain_long_document_spans_pages_without_losing_content():
    from pypdf import PdfReader
    data = render_pdf({'title': 'Raport', 'content': ('Długa treść dokumentu\n' * 180) + 'Koniec dokumentu'})
    pdf = PdfReader(BytesIO(data))
    assert len(pdf.pages) > 1
    assert 'Koniec dokumentu' in pdf.pages[-1].extract_text()


def test_pdf_endpoint_requires_read_access(app_client):
    _, client = app_client
    doc = client.post('/api/documents', json={'title': 'Umowa', 'content': 'Treść umowy'}).json()
    response = client.get(f"/api/documents/{doc['id']}/pdf")
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['content-disposition'].startswith('attachment;')
    assert response.content.startswith(b'%PDF-')
    client.post('/api/logout')
    assert client.get(f"/api/documents/{doc['id']}/pdf").status_code == 401
