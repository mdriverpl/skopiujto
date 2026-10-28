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

DEVICE_SUBJECT = ('Transakcja została wstrzymana. Potwierdź urządzenie, '
                  'z którego logujesz się do bankowości.')
DEVICE_CONTENT = '* to dół numerem\n**801 36 36 36**.\nPKO\nbzns\nAlert bezpieczeństwa #VY2HSMT0UP'


@pytest.mark.parametrize('subject,content', [
    (DEVICE_SUBJECT, DEVICE_CONTENT),
    (DEVICE_SUBJECT, ''),
    ('Potwierdź urządzenie do bankowości internetowej', 'Komunikat bezpieczeństwa'),
    ('Dostęp do konta został zablokowany', 'Zweryfikuj urządzenie do bankowości.'),
    ('Alert bezpieczeństwa', 'Bankowość internetowa: zatwierdź logowanie.'),
])
def test_device_and_banking_access_lures(subject, content):
    assert mail_rules.phishing_reason(subject, content).startswith('Podejrzenie phishingu:')


@pytest.mark.parametrize('sender', [
    'info@soulsantasolomonllc.com', 'info@obca-firma.pl',
    'info@pkobp.pl.attacker.example', 'info@fakepkobp.pl',
])
def test_body_bank_signature_with_device_lure_checks_exact_domain(sender):
    reason = mail_rules.bank_impersonation_reason(sender, 'Konto — Pomoc techniczna',
                                                 DEVICE_SUBJECT, DEVICE_CONTENT)
    assert sender.split('@')[1] in reason


@pytest.mark.parametrize('sender', ['info@pkobp.pl', 'info@alerts.pkobp.pl'])
def test_official_domain_is_not_a_bank_identity_mismatch(sender):
    assert not mail_rules.bank_impersonation_reason(sender, 'Konto', DEVICE_SUBJECT, DEVICE_CONTENT)


@pytest.mark.parametrize('subject,content', [
    ('Potwierdzenie przelewu do PKO', 'Przelew został wysłany.'),
    ('Transakcja została wstrzymana', 'Skontaktuj się ze swoim bankiem.'),
    ('Potwierdź urządzenie do prezentacji', 'Laptop jest gotowy.'),
    ('Materiały edukacyjne', DEVICE_SUBJECT + DEVICE_CONTENT),
    ('Ostrzeżenie przed phishingiem', DEVICE_SUBJECT + DEVICE_CONTENT),
    ('Faktura za usługi', 'Nasz rachunek prowadzony jest w PKO.'),
])
def test_banking_mentions_and_education_are_not_device_lures(subject, content):
    assert not mail_rules.spam_reason(subject, content, 'biuro@example.com', 'Jan Kowalski')


@pytest.mark.parametrize('sender,name,subject,content,expected', [
    ('info@soulsantasolomonllc.com', 'Konto', DEVICE_SUBJECT, DEVICE_CONTENT, 'spam'),
    ('info@obca-firma.pl', 'Konto', DEVICE_SUBJECT, DEVICE_CONTENT, 'spam'),
    ('info@obca-firma.pl', 'PKO Bank Polski', 'Informacja', 'Komunikat', 'spam'),
    ('biuro@example.com', 'Jan Kowalski', 'Faktura za usługi', 'Przesyłam fakturę.', 'inbox'),
    ('biuro@example.pl', 'Jan Kowalski', 'Przelew do PKO', 'Przesyłam potwierdzenie.', 'inbox'),
])
def test_incoming_routing_uses_banking_signals_not_tld(monkeypatch, sender, name, subject, content, expected):
    monkeypatch.setattr(mail_rules, 'context', lambda con, user_id: ({}, set(), set()))
    assert mail_rules.apply_incoming(None, 'user', sender, subject, content, name) == expected


def test_device_lure_import_scan_and_warning_for_existing_spam(app_client):
    main, client = app_client
    row = promotion(client, 'Konto — Pomoc techniczna <info@soulsantasolomonllc.com>',
                    DEVICE_SUBJECT, DEVICE_CONTENT)
    assert row['folder'] == 'spam'
    assert row['category_reason'].startswith('Podejrzenie phishingu:')
    assert 'soulsantasolomonllc.com' in row['phishing_warning']
    # Previously imported inbox messages must be moved by the spam scan.
    with main.db() as con:
        con.execute("UPDATE client_mail SET folder='inbox',category='',category_source='',category_reason='' WHERE id=?", (row['id'],))
    assert client.post('/api/client-mail/spam-scan').json()['moved'] == 1
    listed = next(item for item in client.get('/api/client-mail').json() if item['id'] == row['id'])
    assert listed['folder'] == 'spam' and listed['phishing_warning']


def test_bank_sender_mismatch_also_routes_mail_to_spam(app_client):
    _, client = app_client
    row = promotion(client, 'PKO Bank Polski <info@obca-firma.pl>', 'Informacja', 'Komunikat')
    assert row['folder'] == 'spam'
    assert row['category_reason'].startswith('Podejrzenie phishingu:')


def test_inbox_listing_excludes_spam_and_other_folders(app_client):
    main, client = app_client
    inbox = promotion(client, 'biuro@example.com', 'Zwykła wiadomość', 'Dzień dobry.')
    spam = promotion(client, 'Konto <info@obca-firma.pl>', DEVICE_SUBJECT, DEVICE_CONTENT)
    archive = promotion(client, 'biuro@example.com', 'Do archiwum', 'Dzień dobry.')
    client.patch('/api/client-mail/' + archive['id'], json={'version': archive['version'], 'folder': 'archive'})
    assert {row['id'] for row in client.get('/api/client-mail?folder=inbox').json()} == {inbox['id']}
    assert {row['id'] for row in client.get('/api/client-mail?folder=spam').json()} == {spam['id']}
    assert len(client.get('/api/client-mail').json()) == 3


@pytest.mark.parametrize('sender,name,subject,expected', [
    ('webmaster@72c9eed974.nxcli.io', 'iPKO biznes',
     'Wymagane natychmiastowe działanie: Zaktualizuj aplikację iPKO biznes', True),
    ('webmaster@72c9eed974.nxcli.io', 'PKO Bank Polski', 'Informacja', True),
    ('webmaster@72c9eed974.nxcli.io', 'Obsługa', 'Zaktualizuj aplikację iPKO', True),
    ('info@pkobp.pl.attacker.example', 'PKO', 'Informacja', True),
    ('info@fakepkobp.pl', 'PKO', 'Informacja', True),
    ('info@PKOBP.PL', 'PKO Bank Polski', 'Informacja', False),
    ('info@powiadomienia.pkobp.pl', 'PKO', 'Informacja', False),
    ('info@ipko.pl', 'iPKO biznes', 'Informacja', False),
    ('biuro@example.com', 'Jan Kowalski', 'Potwierdzenie przelewu do PKO', False),
    ('webmaster@72c9eed974.nxcli.io', 'Serwis', 'Aktualizacja strony', False),
])
def test_bank_identity_and_sender_domain_mismatch(sender, name, subject, expected):
    reason = mail_rules.bank_impersonation_reason(sender, name, subject)
    assert bool(reason) is expected
    if expected:
        assert reason.startswith('Podejrzenie phishingu:')
        assert sender.split('@')[1].lower() in reason


def test_bank_impersonation_warning_in_import_listing_and_preview_even_when_assigned(app_client):
    main, client = app_client
    message = promotion(client, 'iPKO biznes <webmaster@72c9eed974.nxcli.io>',
                        'Wymagane natychmiastowe działanie: Zaktualizuj aplikację iPKO biznes',
                        'Pilny komunikat iPKO biznes')
    assert '72c9eed974.nxcli.io' in message['phishing_warning']
    # Existing mail also gets the warning without reimport or a spam scan.
    with main.db() as con:
        con.execute("UPDATE client_mail SET category='',category_reason='',folder='inbox' WHERE id=?", (message['id'],))
    listing = next(row for row in client.get('/api/client-mail').json() if row['id'] == message['id'])
    assert listing['phishing_warning'] == message['phishing_warning']
    preview = client.patch('/api/client-mail/' + message['id'],
                           json={'version': listing['version'], 'unread': False}).json()
    assert preview['phishing_warning'] == message['phishing_warning']
    trusted = assign(client, preview)
    assert trusted.status_code == 200
    assert trusted.json()['phishing_warning'] == message['phishing_warning']


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
