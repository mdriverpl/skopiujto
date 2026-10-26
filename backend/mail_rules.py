"""Private sender rules and company links to entries in the Firmy dictionary."""
import json
import secrets
import re
import unicodedata
from html import unescape
from datetime import timedelta, datetime, timezone
from email.utils import parseaddr

from fastapi import HTTPException
from email_validator import validate_email, EmailNotValidError
from pydantic import BaseModel, Field
from typing import Literal

SCHEMA = '''
CREATE TABLE IF NOT EXISTS client_mail_spam_addresses(
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 address TEXT NOT NULL, PRIMARY KEY(user_id,address));
CREATE TABLE IF NOT EXISTS client_mail_company_rules(
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 scope TEXT NOT NULL CHECK(scope IN ('email','domain')), target TEXT NOT NULL,
 entry_id TEXT NOT NULL REFERENCES dictionary_entries(id) ON DELETE CASCADE,
 PRIMARY KEY(user_id,scope,target));
CREATE TABLE IF NOT EXISTS client_mail_company_exclusions(
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 address TEXT NOT NULL, PRIMARY KEY(user_id,address));
'''


class CompanyLink(BaseModel):
    scope: Literal['email', 'domain'] = 'email'
    entry_id: str | None = Field(default=None, max_length=64)
    name: str = Field(default='', max_length=200)
    version: int = Field(ge=1)


class CompanyUnlink(BaseModel):
    version: int = Field(ge=1)
    entry_id: str = Field(min_length=1, max_length=64)


def address(value):
    try:
        return validate_email(parseaddr(value)[1], check_deliverability=False,
                              allow_smtputf8=False).ascii_email.lower()
    except EmailNotValidError:
        raise HTTPException(422, 'Nadawca nie ma poprawnego adresu e-mail.') from None


def name_field(fields):
    return next((f for f in fields if f.casefold() in ('nazwa', 'firma', 'nazwa firmy')), fields[0])


def companies(con, user_id):
    rows = con.execute('''SELECT e.id,e.values_json,d.fields FROM dictionary_entries e
        JOIN dictionaries d ON d.id=e.dictionary_id
        WHERE d.user_id=? AND lower(d.name)='firmy' ORDER BY e.id''', (user_id,))
    return [{'id': r['id'], 'name': json.loads(r['values_json']).get(name_field(json.loads(r['fields'])), '')}
            for r in rows]


def context(con, user_id):
    entries = {item['id']: item for item in companies(con, user_id)}
    rules = {(r['scope'], r['target']): entries[r['entry_id']] for r in con.execute(
        'SELECT scope,target,entry_id FROM client_mail_company_rules WHERE user_id=?', (user_id,))
        if r['entry_id'] in entries}
    spam = {r['address'] for r in con.execute(
        'SELECT address FROM client_mail_spam_addresses WHERE user_id=?', (user_id,))}
    exclusions = {r['address'] for r in con.execute(
        'SELECT address FROM client_mail_company_exclusions WHERE user_id=?', (user_id,))}
    return rules, spam, exclusions


def government_domain(domain):
    for suffix, country in (('gov.pl', 'Polska'), ('gov.in', 'Indie')):
        if domain == suffix or domain.endswith('.' + suffix):
            return {'domain': domain, 'suffix': suffix, 'country': country,
                    'authentication': 'unverified', 'spam_protected': suffix == 'gov.pl'}
    return None


def classify(sender, rules_context):
    rules, spam, exclusions = rules_context
    try: sender = address(sender)
    except HTTPException: return {'company': None, 'safe': False, 'blocked': False, 'government': None, 'spam_protected': False}
    government = government_domain(sender.split('@')[1])
    company = None if sender in exclusions else rules.get(('email', sender)) or rules.get(('domain', sender.split('@')[1]))
    protected = bool(company) or bool(government and government['spam_protected'])
    blocked = sender in spam and not protected
    return {'company': company, 'safe': bool(company), 'blocked': blocked,
            'government': government, 'spam_protected': protected}


def normalized_text(value):
    value = unicodedata.normalize('NFKD', unescape(value or '').casefold().replace('ł', 'l'))
    return re.sub(r'\s+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).strip()


def bank_impersonation_reason(sender_email, sender_name, subject):
    """Flag a claimed bank identity on an unrelated sender domain.

    Domain matching is only a mismatch check, never proof of authenticity.
    A mention in ordinary correspondence or the body alone is insufficient.
    """
    brand = r'\b(?:ipko|pko(?:\s+bp)?|pko\s+bank\s+polski)\b'
    claimed_sender = re.search(brand, normalized_text(sender_name))
    subject = normalized_text(subject)
    bank_action = re.search(brand, subject) and re.search(
        r'\b(?:zaktualizuj|aktualizacj\w*|zweryfikuj|weryfikacj\w*|'
        r'potwierdz|zablokowan\w*|zawieszon\w*|wymagane|piln\w*)\b', subject)
    if not (claimed_sender or bank_action):
        return ''
    domain = parseaddr(sender_email or '')[1].rsplit('@', 1)[-1].casefold().rstrip('.')
    if any(domain == allowed or domain.endswith('.' + allowed)
           for allowed in ('pkobp.pl', 'ipko.pl', 'inteligo.pl')):
        return ''
    return ('Podejrzenie phishingu: wiadomość podaje się za PKO / iPKO, '
            f'ale domena nadawcy ({domain or "brak domeny"}) nie odpowiada domenom banku. '
            'Nie klikaj linków, nie otwieraj załączników i nie podawaj danych logowania.')


def phishing_reason(subject, content):
    """Detect combined account/payment lures; never trust or block a TLD alone."""
    subject = normalized_text(subject)
    text = normalized_text(content)[:100000]
    # Warnings and normal invoices alone are not credential requests. Require
    # an actionable subject and matching requests in the actual message body.
    update = re.search(r'\b(zaktualizuj|aktualizacj\w*|zweryfikuj|weryfikacj\w*|'
                       r'potwierdz|verify|update|confirm)\b', subject)
    sensitive = re.search(r'\b(platnosci\w*|platnosc|danych|dane|konta|konto|karty|'
                          r'payment\w*|billing|account|card|identity)\b', subject)
    login = re.search(r'\b(zaloguj sie|zalogowac sie|log in|login|sign in|'
                      r'zweryfikuj swoje dane|potwierdz swoje dane|verify your (?:account|identity))\b', text)
    disruption = re.search(r'(przerw\w* w swiadczeniu|nadal korzystac z uslug|'
                           r'konto zostanie (?:zablokowane|zawieszone)|utrat\w* dostepu|'
                           r'unikn\w* (?:blokady|zawieszenia)|account (?:will be |has been )?(?:suspended|blocked)|'
                           r'service interruption|avoid (?:suspension|interruption)|continue using)', text)
    if update and sensitive and login and disruption:
        return 'Podejrzenie phishingu: aktualizacja danych konta lub płatności, żądanie logowania i groźba utraty dostępu do usługi.'
    secrets = re.search(r'(podaj|przeslij|wpisz|enter|provide|send).{0,65}\b('
                        r'haslo|hasla|password|kod (?:sms|blik|jednorazowy)|one.time (?:code|password)|'
                        r'cvv|cvc|pin karty|numer karty)', text)
    link = re.search(r'https?://\S+', text)
    if update and sensitive and secrets and link:
        return 'Podejrzenie phishingu: prośba o poufne dane lub kod autoryzacji przy weryfikacji konta albo płatności.'
    return ''


def spam_reason(subject, content):
    # Phishing checks precede marketing exemptions for invoices and payments.
    return phishing_reason(subject, content) or promotional_reason(subject, content)


def invoice_reason(subject):
    subject = normalized_text(subject)
    match = re.search(r'\b(faktur(?:a|y|e|ze|ami|om|ach)?|invoices?|rechnung(?:en)?|'
                      r'rachun(?:ek|ki|ku|kow)|e[ -]?faktur(?:a|y|e)|pro[ -]?forma)\b|'
                      r'\binv[\s.:#-]*\d', subject)
    return 'Filtr lokalny: temat wskazuje fakturę lub rachunek.' if match else ''


def mark_invoice(con, row, bump_version=False):
    if row['folder'] not in ('inbox', 'archive') or row['category'] == 'spam': return False
    reason = invoice_reason(row['subject'])
    if not reason: return False
    changes = {}
    if not row['label'] and row['label_source'] != 'manual':
        changes.update(label='invoice', label_source='local')
    if not row['category'] and row['category_source'] != 'manual':
        changes.update(category='invoice', category_source='local', category_reason=reason)
    if not changes: return False
    fields = ','.join(f'{key}=?' for key in changes)
    if bump_version: fields += ',version=version+1'
    con.execute(f'UPDATE client_mail SET {fields} WHERE id=? AND user_id=?',
                (*changes.values(), row['id'], row['user_id']))
    return True


def promotional_reason(subject, content):
    """Local filter requiring several matching advertising signals."""
    subject = normalized_text(subject)
    content = normalized_text(content)[:100000]
    if re.search(r'\b(re|fwd?|faktura|invoice|zamowienie|order|platnosc|payment|potwierdzenie)\b', subject):
        return ''
    commercial = re.search(r'\b(kup|kupuj|promocj\w*|rabat\w*|wyprzedaz\w*|oferta specjalna|'
                           r'zainwestuj|inwestuj|apartament\w*|discount\w*|sale|special offer|buy now)\b', subject)
    bulk = re.search(r'(rezygnacj\w* z otrzymywania|wypisz sie|wypisac sie|anuluj subskrypcj|'
                     r'unsubscribe|opt.out|nie chcesz otrzymywac|otrzymujesz (ten|te) (mail|wiadomosc))', content)
    if commercial and bulk:
        return 'Filtr lokalny: oferta reklamowa w temacie oraz możliwość wypisania z masowej wysyłki.'
    benefit = re.search(r'\b(spokojny sen|lepszy sen|spij lepiej|kazdej nocy|mlodsza skora|'
                        r'pozbadz sie zmarszczek|schudnij|plaski brzuch)\b', subject)
    product = re.search(r'\b(poduszk\w*|materac\w*|suplement\w*|krem\w*|kapsulk\w*)\b', content)
    call_to_action = re.search(r'\b(wyprobuj|kup|zamow|skorzystaj z oferty)\b', content)
    if benefit and product and call_to_action:
        return 'Filtr lokalny: reklamowa obietnica korzyści, opis produktu i zachęta do zakupu lub wypróbowania.'
    # Inspect the full message, not just the subject. Strip URLs so tracking
    # parameters cannot accidentally supply commercial words.
    text = re.sub(r'https?://\S+', ' ', content)
    bulk = bulk or re.search(r'(mailing wyslany|wyslano na zlecenie|newsletter|'
                             r'zrezygn\w* z otrzymywania|otrzymujesz powiadomienia e.mail)', text)
    offer = re.search(r'\b(promocj\w*|rabat\w*|kupon\w*|wyprzedaz\w*|oferta dla firm|'
                      r'pakiet medyczny|prywatna opieka medyczna|darmowe wi.?fi|'
                      r'odblokuj pelna liste dzieki premium)\b', subject + ' ' + text)
    discount = re.search(r'(?:[-−–]\s*\d{1,3}\s*%|\b\d{1,3}\s*%\s*(?:taniej|rabatu))', subject)
    sales_action = re.search(r'\b(zgarnij|wyprobuj|kup teraz|zamow teraz|zapytaj o (?:oferte|wycene)|'
                             r'zostaw (?:kontakt|dane)|zapisz sie na szkoleni\w*|'
                             r'odbierz (?:darmow\w*|\d+\s*zl)|skorzystaj z oferty)\b', text + ' ' + subject)
    if bulk and (commercial or discount or offer or sales_action):
        return 'Filtr lokalny: masowa wysyłka połączona z ofertą, rabatem lub zachętą sprzedażową.'
    if re.search(r'\bnielimitowany internet\b', subject) and offer and sales_action:
        return 'Filtr lokalny: reklama internetu z obietnicą darmowej usługi i zachętą do odbioru.'
    if re.search(r'\b(szkoleni\w*|nowosci|zmiany)\b', subject) and re.search(r'\bszkoleni\w*\b', text) and sales_action:
        return 'Filtr lokalny: promocyjna oferta szkoleń z zachętą do zapisania się.'
    permission = re.search(r'\b(prosba o zgode|zgoda na (?:kontakt|przeslanie|przedstawienie))\b', subject)
    service_pitch = re.search(r'\b(profilem firmowym|marketing\w*|promocje|nasz\w* ofert\w*|'
                              r'oferujemy|oferuje|uslug\w*|facebook\w*)\b', text)
    contact_pitch = re.search(r'\b(zapraszam do kontaktu|zapraszamy do kontaktu|'
                              r'czy moge przeslac|czy mozemy przeslac|przeslanie oferty)\b', text)
    if permission and service_pitch and contact_pitch:
        return 'Filtr lokalny: niezamówiona propozycja usług lub prośba o zgodę na ofertę handlową.'
    social_digest = re.search(r'(sugerowane aktualizacje|wlasnie opublikowal\w* cos|'
                              r'\d+ osob\w* wyswietlil\w* twoj profil)', subject + ' ' + text)
    if bulk and social_digest:
        return 'Filtr lokalny: masowy newsletter z rekomendacjami lub promocją aktywności społecznościowej.'
    return ''


def apply_incoming(con, user_id, sender, subject='', content=''):
    status = classify(sender, context(con, user_id))
    if status['blocked']: return 'spam'
    if status['spam_protected']: return 'inbox'
    return 'spam' if spam_reason(subject, content) else 'inbox'


def scan_inbox(con, user_id, cutoff=None):
    rules_context = context(con, user_id)
    restore_trusted_spam(con, user_id, rules_context)
    moved = 0
    query = "SELECT * FROM client_mail WHERE user_id=? AND folder='inbox'"
    params = (user_id,)
    if cutoff is not None:
        query += ' AND created_at>=?'
        params += ((cutoff - timedelta(days=1)).date().isoformat(),)
    for row in con.execute(query, params).fetchall():
        if cutoff is not None:
            try:
                stamp = datetime.fromisoformat(row['created_at'].replace('Z', '+00:00'))
                if stamp.tzinfo is None: stamp = stamp.replace(tzinfo=timezone.utc)
                if stamp < cutoff: continue
            except (ValueError, TypeError, AttributeError): continue
        status = classify(row['sender_email'], rules_context)
        if status['spam_protected'] or row['category_source'] == 'manual': continue
        reason = ('Adres nadawcy na Twojej liście spamu.' if status['blocked'] else
                  spam_reason(row['subject'], row['content']))
        if not reason: continue
        con.execute("""UPDATE client_mail SET folder='spam',category='spam',category_source='local',
            category_reason=?,version=version+1 WHERE id=?""", (reason, row['id']))
        moved += 1
    for row in con.execute("SELECT * FROM client_mail WHERE user_id=? AND folder IN ('inbox','archive')", (user_id,)).fetchall():
        mark_invoice(con, row, bump_version=True)
    return moved


def restore_trusted_spam(con, user_id, rules_context=None):
    rules_context = rules_context if rules_context is not None else context(con, user_id)
    restored = 0
    for row in con.execute("SELECT id,sender_email,folder,category FROM client_mail WHERE user_id=? AND (folder='spam' OR category='spam')", (user_id,)).fetchall():
        if not classify(row['sender_email'], rules_context)['spam_protected']: continue
        con.execute("""UPDATE client_mail SET folder=?,category=CASE WHEN category='spam' THEN '' ELSE category END,
            category_source=CASE WHEN category='spam' THEN '' ELSE category_source END,
            category_reason=CASE WHEN category='spam' THEN '' ELSE category_reason END,
            version=version+1 WHERE id=?""", ('inbox' if row['folder'] == 'spam' else row['folder'], row['id']))
        restored += 1
    return restored


def mark_incoming(con, identifier, user_id):
    row = con.execute('SELECT * FROM client_mail WHERE id=? AND user_id=?', (identifier, user_id)).fetchone()
    if row['folder'] != 'spam':
        mark_invoice(con, row)
        return
    status = classify(row['sender_email'], context(con, user_id))
    reason = ('Adres nadawcy na Twojej liście spamu.' if status['blocked'] else
              spam_reason(row['subject'], row['content']))
    if reason:
        con.execute("UPDATE client_mail SET category='spam',category_source='local',category_reason=? WHERE id=?",
                    (reason, identifier))


def link(con, user_id, sender, body, now):
    sender = address(sender)
    dictionary = con.execute("SELECT * FROM dictionaries WHERE user_id=? AND lower(name)='firmy'", (user_id,)).fetchone()
    entry = None
    if body.entry_id:
        if dictionary:
            entry = con.execute('SELECT * FROM dictionary_entries WHERE id=? AND dictionary_id=?',
                                (body.entry_id, dictionary['id'])).fetchone()
        if not entry: raise HTTPException(404, 'Nie znaleziono firmy w Twoim słowniku Firmy.')
    else:
        name = body.name.strip()
        if not name: raise HTTPException(422, 'Wybierz firmę lub podaj jej nazwę.')
        if not dictionary:
            identifier = secrets.token_hex(16)
            con.execute('INSERT INTO dictionaries(id,user_id,name,fields,created_at) VALUES(?,?,?,?,?)',
                        (identifier, user_id, 'Firmy', json.dumps(['Nazwa'], ensure_ascii=False), now()))
            dictionary = con.execute('SELECT * FROM dictionaries WHERE id=?', (identifier,)).fetchone()
        field = name_field(json.loads(dictionary['fields']))
        for candidate in con.execute('SELECT * FROM dictionary_entries WHERE dictionary_id=?', (dictionary['id'],)):
            if json.loads(candidate['values_json']).get(field, '').strip().casefold() == name.casefold():
                entry = candidate
                break
        if not entry:
            identifier = secrets.token_hex(16)
            values = {f: name if f == field else '' for f in json.loads(dictionary['fields'])}
            con.execute('INSERT INTO dictionary_entries(id,dictionary_id,values_json,updated_at) VALUES(?,?,?,?)',
                        (identifier, dictionary['id'], json.dumps(values, ensure_ascii=False), now()))
            entry = {'id': identifier}
    target = sender if body.scope == 'email' else sender.split('@')[1]
    con.execute('''INSERT INTO client_mail_company_rules(user_id,scope,target,entry_id) VALUES(?,?,?,?)
        ON CONFLICT(user_id,scope,target) DO UPDATE SET entry_id=excluded.entry_id''',
        (user_id, body.scope, target, entry['id']))
    con.execute('DELETE FROM client_mail_company_exclusions WHERE user_id=? AND address=?', (user_id, sender))
    # Assigning a company explicitly trusts these senders again.
    if body.scope == 'email':
        con.execute('DELETE FROM client_mail_spam_addresses WHERE user_id=? AND address=?', (user_id, sender))
    else:
        con.execute("DELETE FROM client_mail_spam_addresses WHERE user_id=? AND split_part(address,'@',2)=?", (user_id, target))
    rules_context = context(con, user_id)
    for message in con.execute("SELECT id,sender_email FROM client_mail WHERE user_id=? AND folder='spam'", (user_id,)).fetchall():
        try: candidate = address(message['sender_email'])
        except HTTPException: continue
        matches = candidate == target if body.scope == 'email' else candidate.split('@')[1] == target
        if matches and classify(candidate, rules_context)['safe']:
            con.execute("UPDATE client_mail SET folder='inbox',version=version+1 WHERE id=?", (message['id'],))
            con.execute("""UPDATE client_mail SET category='',category_source='',category_reason=''
                WHERE id=? AND category='spam'""", (message['id'],))
    restore_trusted_spam(con, user_id, rules_context)


def unlink_email(con, user_id, sender, entry_id):
    sender = address(sender)
    company = classify(sender, context(con, user_id))['company']
    if not company or company['id'] != entry_id:
        raise HTTPException(409, 'Przypisanie firmy zostało zmienione. Odśwież pocztę.')
    con.execute("DELETE FROM client_mail_company_rules WHERE user_id=? AND scope='email' AND target=?", (user_id, sender))
    # An address-level exception prevents inheriting the domain's company again.
    # Neither the domain rule nor the dictionary entry is removed.
    con.execute('INSERT INTO client_mail_company_exclusions(user_id,address) VALUES(?,?) ON CONFLICT DO NOTHING', (user_id, sender))
    for row in con.execute('SELECT id,sender_email FROM client_mail WHERE user_id=?', (user_id,)).fetchall():
        try: matches = address(row['sender_email']) == sender
        except HTTPException: continue
        if matches:
            con.execute('UPDATE client_mail SET version=version+1 WHERE id=?', (row['id'],))
