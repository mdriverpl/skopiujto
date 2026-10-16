from email.message import EmailMessage

import pytest
from backend import mail_rules
from backend.test_storage import app_client


@pytest.mark.parametrize('subject', ['Faktura VAT 12/2026', 'E-faktura za usługi', 'Twoje faktury',
    'Przesyłamy fakturę', 'Hetzner Online GmbH - Invoice 086001223006 (K1222559317)',
    'INVOICE #123', 'Invoices for October', 'Rechnung Nr. 456', 'Rachunek za telefon',
    'Pro forma 20/2026', 'INV-12345'])
def test_invoice_subject_variants(subject):
    assert mail_rules.invoice_reason(subject)


@pytest.mark.parametrize('subject', ['Invitation to meeting', 'Oferta systemu do fakturowania',
    'Rachunkowość dla firm', 'Rozliczenie czasu pracy', 'InvoiceManager newsletter'])
def test_unrelated_words_are_not_invoice_subjects(subject):
    assert not mail_rules.invoice_reason(subject)


def receive(client, subject='Invoice 123', content='Your invoice is attached.'):
    message = EmailMessage()
    message['From'] = 'billing@example.com'
    message['Subject'] = subject
    message.set_content(content)
    result = client.post('/api/client-mail/import', files={'file': ('mail.eml', message.as_bytes())})
    assert result.status_code == 201, result.text
    return result.json()


def test_incoming_invoice_gets_label_and_category_and_manual_clear_persists(app_client):
    _, client = app_client
    row = receive(client)
    assert row['label'] == row['category'] == 'invoice'
    assert row['label_source'] == row['category_source'] == 'local'
    assert row['version'] == 1
    row = client.patch('/api/client-mail/' + row['id'], json={'version': 1, 'label': '', 'category': ''}).json()
    assert row['label_source'] == 'manual'
    client.post('/api/client-mail/spam-scan')
    row = next(m for m in client.get('/api/client-mail').json() if m['id'] == row['id'])
    assert row['label'] == row['category'] == ''


def test_existing_invoice_is_labeled_without_overwriting_urgent_or_manual_categories(app_client):
    main, client = app_client
    old = receive(client, 'Dostarczenie dokumentu')
    urgent = receive(client, 'Dokument')
    client.patch('/api/client-mail/' + urgent['id'], json={'version': 1, 'label': 'urgent', 'category': 'correspondence'})
    with main.db() as con:
        con.execute("UPDATE client_mail SET subject='Faktura VAT 123' WHERE user_id=?", (old['user_id'],))
    client.post('/api/client-mail/spam-scan')
    rows = {m['id']: m for m in client.get('/api/client-mail').json()}
    assert rows[old['id']]['label'] == rows[old['id']]['category'] == 'invoice'
    assert rows[old['id']]['version'] == 2
    assert rows[urgent['id']]['label'] == 'urgent'
    assert rows[urgent['id']]['category'] == 'correspondence'
    client.post('/api/client-mail/spam-scan')
    assert next(m for m in client.get('/api/client-mail').json() if m['id'] == old['id'])['version'] == 2


def test_phishing_takes_precedence_over_invoice_subject(app_client):
    _, client = app_client
    row = receive(client, 'Invoice: verify your billing account',
                  'Sign in to verify your account and avoid service interruption.')
    assert row['folder'] == row['category'] == 'spam'
    assert row['label'] == ''
