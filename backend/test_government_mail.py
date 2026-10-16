import pytest
from backend import mail_rules
from backend.test_storage import app_client
from backend.test_mail_spam_filter import promotion
from backend.test_mail_phishing import PAYMENT_LURE


@pytest.mark.parametrize('domain,expected', [
    ('gov.pl', 'Polska'), ('ministerstwo.gov.pl', 'Polska'), ('mail.urzad.gov.pl', 'Polska'),
    ('diksha.gov.in', 'Indie'), ('gov.pl.example.com', None), ('evilgov.pl', None), ('govpl.com', None),
])
def test_government_suffix_matches_only_exact_domain_boundaries(domain, expected):
    result = mail_rules.government_domain(domain)
    assert (result['country'] if result else None) == expected
    if result: assert result['authentication'] == 'unverified'


def test_gov_pl_is_protected_but_never_presented_as_authenticated_email(app_client):
    _, client = app_client
    message = promotion(client, 'biuro@urzad.gov.pl', 'Zaktualizuj szczegóły płatności', PAYMENT_LURE)
    assert message['folder'] == 'inbox' and message['spam_protected'] and not message['safe']
    assert message['government']['country'] == 'Polska'
    assert message['government']['authentication'] == 'unverified'
    assert message['phishing_warning'].startswith('Podejrzenie phishingu:')
    url = '/api/client-mail/' + message['id']
    assert client.post(url + '/spam-address', json={'version': message['version']}).status_code == 422
    for change in ({'folder': 'spam'}, {'category': 'spam'}):
        assert client.patch(url, json={'version': message['version'], **change}).status_code == 422
    assert client.post('/api/client-mail/spam-scan').json()['moved'] == 0
    assert client.get('/api/client-mail').json()[0]['folder'] == 'inbox'


def test_foreign_government_sender_and_polish_lookalike_are_not_exempt_from_filter(app_client):
    _, client = app_client
    foreign = promotion(client, 'supportemail@diksha.gov.in', 'Zaktualizuj szczegóły płatności', PAYMENT_LURE)
    assert foreign['government']['country'] == 'Indie'
    assert not foreign['spam_protected'] and foreign['folder'] == 'spam'
    fake = promotion(client, 'support@urzad.gov.pl.example.com', 'Zaktualizuj szczegóły płatności', PAYMENT_LURE)
    assert fake['government'] is None and fake['folder'] == 'spam'


def test_old_gov_pl_spam_and_address_blocks_are_restored_without_losing_other_categories(app_client):
    main, client = app_client
    message = promotion(client, 'biuro@urzad.gov.pl', 'Informacja', 'Informacja urzędowa.')
    with main.db() as con:
        con.execute("UPDATE client_mail SET folder='spam',category='spam' WHERE id=?", (message['id'],))
        con.execute('INSERT INTO client_mail_spam_addresses(user_id,address) SELECT user_id,sender_email FROM client_mail WHERE id=?', (message['id'],))
    client.post('/api/client-mail/spam-scan')
    row = client.get('/api/client-mail').json()[0]
    assert row['folder'] == 'inbox' and row['category'] == '' and not row['blocked']
