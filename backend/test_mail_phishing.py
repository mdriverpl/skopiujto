from email.message import EmailMessage
import pytest

from backend import mail_rules
from backend.client_mail import parse_message
from backend.test_storage import app_client
from backend.test_mail_spam_filter import promotion
from backend.test_mail_rules import assign

PAYMENT_LURE = ('Zaktualizuj informacje o swoim koncie. Szanowny Kliencie! '
                'Aby nadal korzystać z usługi, sprawdź swoje dane i uniknij przerw w świadczeniu usług. '
                'Zaloguj się na moje konto.')


@pytest.mark.parametrize('subject,content', [
    ('Zaktualizuj szczegóły płatności', PAYMENT_LURE),
    ('Aktualizacja danych płatności', PAYMENT_LURE),
    ('Płatność — zweryfikuj swoje konto', PAYMENT_LURE),
    ('Faktura: potwierdź dane konta', PAYMENT_LURE),
    ('Update your billing information', 'Sign in to verify your account and avoid service interruption.'),
    ('Confirm your account', 'Provide your password at https://login.example.invalid/verify'),
    ('Zweryfikuj dane płatności', 'Wpisz kod SMS na https://verify.example.invalid/'),
])
def test_phishing_lures_are_detected_before_marketing_exemptions(subject, content):
    assert mail_rules.spam_reason(subject, content).startswith('Podejrzenie phishingu:')


@pytest.mark.parametrize('subject,content', [
    ('Faktura za październik', 'W załączniku faktura. Termin płatności 14 dni.'),
    ('Aktualizacja danych płatności', 'Zmieniliśmy numer naszego rachunku. Prosimy o kontakt telefoniczny.'),
    ('Zaktualizuj swoje konto', 'Adres korespondencyjny możesz zmienić w ustawieniach profilu.'),
    ('Ostrzeżenie przed phishingiem', PAYMENT_LURE),
    ('Materiały edukacyjne', 'Materiały są dostępne na platformie edukacyjnej.'),
    ('Kod logowania', 'Twój kod to 123456. Nie udostępniaj go nikomu.'),
])
def test_normal_correspondence_and_security_education_are_not_phishing(subject, content):
    assert not mail_rules.phishing_reason(subject, content)


def test_payment_lure_import_and_existing_mail_scan_preserve_trusted_domain(app_client):
    main, client = app_client
    row = promotion(client, 'supportemail@diksha.gov.in', 'Zaktualizuj szczegóły płatności', PAYMENT_LURE)
    assert row['folder'] == 'spam' and row['category_source'] == 'local'
    assert row['category_reason'].startswith('Podejrzenie phishingu:')
    with main.db() as con:
        con.execute("UPDATE client_mail SET folder='inbox',category='',category_source='',category_reason='' WHERE id=?", (row['id'],))
    assert client.post('/api/client-mail/spam-scan').json()['moved'] == 1
    row = next(item for item in client.get('/api/client-mail').json() if item['id'] == row['id'])
    trusted = assign(client, row, scope='domain')
    assert trusted.status_code == 200 and trusted.json()['safe']
    assert promotion(client, 'other@diksha.gov.in', 'Zaktualizuj szczegóły płatności', PAYMENT_LURE)['folder'] == 'inbox'
    ordinary = promotion(client, 'contact@another.gov.in', 'Materiały edukacyjne', 'Informacja o szkoleniu.')
    assert ordinary['folder'] == 'inbox'


def test_html_import_keeps_actual_link_target_as_plain_text_without_executing_html():
    message = EmailMessage()
    message['From'] = 'sender@example.com'
    message['Subject'] = 'Zweryfikuj dane płatności'
    message.set_content('<p>Wpisz kod SMS</p><a href="https://verify.example.invalid/login">Oficjalne konto</a>'
                        '<script>secret()</script><a href="javascript:secret()">Niebezpieczny skrypt</a>', subtype='html')
    parsed = parse_message(message.as_bytes())
    assert 'Oficjalne konto (https://verify.example.invalid/login)' in parsed['content']
    assert 'secret()' not in parsed['content']
    assert '<a' not in parsed['content'] and '<script' not in parsed['content']
    assert mail_rules.spam_reason(parsed['subject'], parsed['content']).startswith('Podejrzenie phishingu:')
