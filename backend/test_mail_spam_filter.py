"""Local promotional filtering: no network or AI service is used."""
from email.message import EmailMessage
import pytest

from backend.mail_rules import promotional_reason
from backend.test_storage import app_client
from backend.test_mail_rules import assign


def promotion(client, sender='reklama@example.com', subject='Kup apartament 5 ★ — zainwestuj w sukces',
              content='Zobacz ofertę. Rezygnacja z otrzymywania wiadomości.'):
    message = EmailMessage()
    message['From'] = sender
    message['Subject'] = subject
    message.set_content(content)
    response = client.post('/api/client-mail/import', files={'file': ('mail.eml', message.as_bytes())})
    assert response.status_code == 201, response.text
    return response.json()


def test_local_signals_require_both_commercial_subject_and_bulk_content():
    assert promotional_reason('Kup apartament', 'Rezygnacja z otrzymywania wiadomości')
    assert promotional_reason('Promocja -30%', 'Unsubscribe')
    assert not promotional_reason('Oferta naprawy laptopa', 'Rezygnacja z otrzymywania wiadomości')
    assert not promotional_reason('Kup apartament', 'Proszę o odpowiedź w sprawie spotkania')
    assert not promotional_reason('Re: Kup apartament', 'Unsubscribe')
    assert not promotional_reason('Faktura za apartament', 'Unsubscribe')


PRODUCT_SUBJECT = 'Spokojny sen każdej nocy!'
PRODUCT_CONTENT = ('Twoja poduszka mo&#380;e by&#263; jeszcze wygodniejsza! '
                   'Wypr&#243;buj Derila i poczuj r&#243;&#380;nic&#281; ju&#380; tej nocy.')

CAMPAIGNS = [
    ('Nowości i zmiany w VAT', 'Profesjonalne szkolenia podatkowe. Zapisz się na szkolenia on-line.'),
    ('Nielimitowany internet w 175 krajach', 'Podróżuj sprytniej. ODBIERZ DARMOWE WIFI NA PODRÓŻ.'),
    ('Niech jesień nabierze smaku! Do -15% na wybrane produkty',
     'Mailing wysłany na zlecenie serwisu. Jeśli nie chcesz otrzymywać tych informacji, kliknij tutaj.'),
    ('Prywatna opieka medyczna dla pracowników Twojej firmy',
     'Pakiet medyczny dla firmy. Zostaw kontakt, doradca przygotuje wycenę. Rezygnacja  z otrzymywania wiadomości.'),
    ('Prośba o zgodę', 'Zaopiekuję się profilem firmowym na Facebooku, zadbam o promocję. Zapraszam do kontaktu.'),
    ('Zgarnij -50% na subskrypcję', 'Zobacz podgląd wiadomości. Rezygnacja z otrzymywania wiadomości.'),
    ('100 za 300 na produkty', 'Odbierz 100zł na kupon. Twój rabat. Jeśli chcesz zrezygnować z otrzymywania komunikacji, kliknij tutaj.'),
    ('Firma właśnie opublikowała coś, co może Cię zainteresować',
     'Sugerowane aktualizacje. Otrzymujesz powiadomienia e-mail z portalu.'),
    ('1 osoba wyświetliła Twój profil',
     'Odblokuj pełną listę dzięki Premium. Otrzymujesz powiadomienia e-mail z portalu.'),
]


@pytest.mark.parametrize('subject,content', CAMPAIGNS)
def test_marketing_campaigns_are_detected_from_multiple_signals(subject, content):
    assert promotional_reason(subject, content)


@pytest.mark.parametrize('subject,content', [
    ('Nowości i zmiany w VAT', 'Proszę uwzględnić nową stawkę w rozliczeniu naszej firmy.'),
    ('Prośba o zgodę', 'Proszę o zgodę na urlop w następnym tygodniu.'),
    ('Prośba o zgodę', 'Proszę o zgodę na wykorzystanie danych w dokumentacji projektu.'),
    ('Oferta naprawy laptopa', 'Przesyłam uzgodnioną wycenę naprawy. Proszę o akceptację.'),
    ('Potwierdzenie zamówienia', 'Odbierz kupon na kolejny zakup. Newsletter.'),
    ('Faktura za usługi', 'Oferta dla firm. Rezygnacja z otrzymywania wiadomości.'),
    ('Re: Promocja produktu', 'Odbierz darmowe produkty. Unsubscribe.'),
    ('Kod logowania do portalu', 'Twój kod to 123456. Nie udostępniaj go innym. Unsubscribe.'),
    ('Nowa wiadomość od klienta', 'Zapraszam do kontaktu w sprawie projektu.'),
])
def test_client_transactional_and_noncommercial_correspondence_is_preserved(subject, content):
    assert not promotional_reason(subject, content)


def test_campaigns_are_filtered_on_import_and_trusted_domain_exempts_every_case(app_client):
    _, client = app_client
    first = None
    for subject, content in CAMPAIGNS:
        ad = promotion(client, subject=subject, content=content)
        assert ad['folder'] == 'spam', subject
        first = first or ad
    assert assign(client, first, scope='domain').status_code == 200
    for subject, content in CAMPAIGNS:
        safe = promotion(client, subject=subject, content=content)
        assert safe['folder'] == 'inbox' and safe['safe'], subject


def test_product_ad_without_unsubscribe_is_detected_including_html_entities():
    assert promotional_reason(PRODUCT_SUBJECT, PRODUCT_CONTENT)
    assert promotional_reason(PRODUCT_SUBJECT, 'Twoja poduszka może być wygodniejsza! Wypróbuj Derila.')
    assert not promotional_reason(PRODUCT_SUBJECT, 'Dziękuję za pomoc. Poduszka jest wygodna.')
    assert not promotional_reason('Re: ' + PRODUCT_SUBJECT, PRODUCT_CONTENT)
    assert not promotional_reason('Faktura za poduszkę', PRODUCT_CONTENT)
    assert not promotional_reason('Proszę wypróbować poduszkę', 'Wypróbuj poduszkę przed następnym spotkaniem.')


def test_product_ad_is_filtered_and_safe_domain_still_bypasses_filter(app_client):
    _, client = app_client
    ad = promotion(client, 'ovfirmy@inklowse.store', PRODUCT_SUBJECT, PRODUCT_CONTENT)
    assert ad['folder'] == 'spam' and ad['category_source'] == 'local'
    assert 'produktu' in ad['category_reason']
    trusted = assign(client, ad, scope='domain')
    assert trusted.status_code == 200 and trusted.json()['safe']
    again = promotion(client, 'inny@inklowse.store', PRODUCT_SUBJECT, PRODUCT_CONTENT)
    assert again['folder'] == 'inbox' and again['safe']


def test_import_filters_ads_but_exempts_exact_trusted_domain_and_address(app_client):
    _, client = app_client
    first = promotion(client)
    assert first['folder'] == 'spam' and first['category_source'] == 'local'
    assert first['category'] == 'spam' and first['category_reason']
    trusted = assign(client, first, scope='domain').json()
    assert trusted['safe'] and trusted['folder'] == 'inbox' and not trusted['category']
    assert promotion(client, 'inny@example.com')['folder'] == 'inbox'
    assert promotion(client, 'inny@sub.example.com')['folder'] == 'spam'
    assert promotion(client, 'inny@otherexample.com')['folder'] == 'spam'
    single = promotion(client, 'jan@another.com')
    assert assign(client, single, scope='email').status_code == 200
    assert promotion(client, 'jan@another.com')['folder'] == 'inbox'
    assert promotion(client, 'ktos@another.com')['folder'] == 'spam'


def test_scan_existing_is_idempotent_and_manual_restore_is_respected(app_client):
    main, client = app_client
    first = promotion(client)
    # Simulate a message stored before automatic filtering was introduced.
    with main.db() as con:
        con.execute("UPDATE client_mail SET folder='inbox',category='',category_source='',category_reason='' WHERE id=?", (first['id'],))
    assert client.post('/api/client-mail/spam-scan').json()['moved'] == 1
    assert client.post('/api/client-mail/spam-scan').json()['moved'] == 0
    row = next(m for m in client.get('/api/client-mail').json() if m['id'] == first['id'])
    restored = client.patch('/api/client-mail/' + row['id'], json={'version': row['version'], 'folder': 'inbox'})
    assert restored.status_code == 200
    assert restored.json()['category_source'] == 'manual' and not restored.json()['category']
    assert client.post('/api/client-mail/spam-scan').json()['moved'] == 0
    assert client.get('/api/client-mail').json()[0]['folder'] == 'inbox'
