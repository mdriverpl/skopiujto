from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader
from pydantic import ValidationError

from backend.pricing_offer import OfferConfig, quote_rows, render_offer, router


@pytest.mark.parametrize('origin', ['http://127.0.0.1:5174', 'http://localhost:5174'])
def test_local_pricing_page_can_download_pdf_through_security_middleware(origin):
    from backend.main import app
    response = TestClient(app).post('/api/pricing/offer', headers={'Origin': origin}, json={
        'users': 19, 'storage': 100, 'server_plan': 'S1',
    })
    assert response.status_code == 200
    assert response.content.startswith(b'%PDF-')


def test_pricing_pdf_rejects_untrusted_browser_origins():
    from backend.main import app
    response = TestClient(app).post('/api/pricing/offer', headers={'Origin': 'https://untrusted.example'}, json={
        'users': 19, 'storage': 100, 'server_plan': 'S1',
    })
    assert response.status_code == 403


def test_vpn_is_optional_costs_19_and_full_configuration_stays_on_one_page():
    config = OfferConfig(users=19, storage=100, server_plan='S1', server_ha=True,
                         database_plan='S1', database_ha=True, waf=True, backup=True, logs=True, vpn=True)
    rows = quote_rows(config)
    assert next(row[2] for row in rows if row[0] == 'VPN') == 19
    reader = PdfReader(BytesIO(render_offer(config)))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert 'VPN' in text
    assert '972,60 zł' in text


def test_public_offer_is_a_pdf_and_includes_polish_text_and_total():
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post('/api/pricing/offer', json={
        'users': 19, 'storage': 100, 'server_plan': 'S1', 'server_ha': True,
        'database_plan': 'S1', 'database_ha': True, 'waf': True, 'backup': True, 'logs': True,
    })
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'no-store'
    assert 'SpaceFlow-oferta.pdf' in response.headers['content-disposition']
    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    for expected in ('Twoja przestrzeń.', 'PostgreSQL S1', 'Analiza logów', '953,60 zł', 'wdrożenie', 'NIS2'):
        assert expected.lower() in text.lower()


def test_no_database_ignores_database_ha_and_unselected_addons():
    config = OfferConfig(users=20, storage=100, server_plan='S2', database_ha=True)
    rows = quote_rows(config)
    assert float(sum(row[2] for row in rows)) == 650.45
    assert rows[3][2] == 0
    assert not any(row[0] in ('WAF', 'Backup S3', 'Analiza logów') for row in rows)
    assert render_offer(config).startswith(b'%PDF-')


@pytest.mark.parametrize('changes', [
    {'users': 0}, {'users': 501}, {'storage': 150}, {'server_plan': 'S99'},
    {'database_engine': '<script>'}, {'total': 1},
])
def test_invalid_configuration_or_client_price_is_rejected(changes):
    with pytest.raises(ValidationError):
        OfferConfig(**({'users': 20, 'storage': 100, 'server_plan': 'S1'} | changes))
