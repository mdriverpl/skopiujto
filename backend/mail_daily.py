"""Private, entirely local daily mail statistics and summaries."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import Depends
from pydantic import BaseModel
from backend import mail_rules

WARSAW = ZoneInfo('Europe/Warsaw')
CATEGORIES = ('spam', 'advertisement', 'invoice', 'payment', 'order', 'newsletter',
              'notification', 'correspondence', 'other', 'uncategorized')


class DayRequest(BaseModel):
    day: date


def parsed_time(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None: stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(WARSAW)
    except (ValueError, TypeError, AttributeError, OverflowError): return None


def parsed_day(value):
    stamp = parsed_time(value)
    return stamp.date() if stamp else None


def statistics(con, user_id, day):
    counts = {'total': 0, 'received': 0, 'sent': 0, 'spam': 0, 'clients': 0,
              'unread': 0, 'urgent': 0, 'reply': 0, 'payment': 0, 'info': 0,
              'categories': dict.fromkeys(CATEGORIES, 0)}
    companies, messages = {}, []
    rules = mail_rules.context(con, user_id)
    rows = con.execute('''SELECT id,sender_name,sender_email,subject,folder,category,label,unread,created_at FROM client_mail
        WHERE user_id=? AND folder!='drafts' ''', (user_id,))
    for row in rows:
        stamp = parsed_time(row['created_at'])
        if not stamp or stamp.date() != day: continue
        counts['total'] += 1
        status = mail_rules.classify(row['sender_email'], rules)
        sent = row['folder'] == 'sent'
        spam = not sent and not status['safe'] and (row['folder'] == 'spam' or row['category'] == 'spam' or status['blocked'])
        saved_category = '' if status['safe'] and row['category'] == 'spam' else row['category']
        category = 'spam' if spam else ('invoice' if row['label'] == 'invoice' else saved_category or 'uncategorized')
        if category not in counts['categories']: category = 'other'
        messages.append({key: row[key] for key in ('id', 'sender_name', 'sender_email', 'subject', 'folder', 'label', 'unread')})
        messages[-1].update(created_at=stamp.isoformat(), category=category, company=status['company'],
                            spam=spam, direction='sent' if sent else 'received')
        if row['folder'] == 'sent':
            counts['sent'] += 1
            continue
        counts['received'] += 1
        counts['categories'][category] += 1
        counts['spam'] += int(spam)
        counts['unread'] += int(bool(row['unread']))
        if not spam:
            counts['urgent'] += int(row['label'] == 'urgent')
            counts['reply'] += int(row['label'] == 'reply')
            counts['payment'] += int(row['label'] == 'payment')
            counts['info'] += int(row['label'] == 'info')
            if status['company']:
                counts['clients'] += 1
                company = status['company']
                companies.setdefault(company['id'], {**company, 'count': 0})['count'] += 1
    return {'day': day.isoformat(), 'timezone': 'Europe/Warsaw', 'stats': counts,
            'messages': sorted(messages, key=lambda item: (datetime.fromisoformat(item['created_at']), item['id']), reverse=True),
            'companies': sorted(companies.values(), key=lambda item: (-item['count'], item['name'])),
            'analysis': local_summary(counts), 'engine': 'local'}


def local_summary(stats):
    advice = []
    if stats['reply']: advice.append(f"Odpowiedz na wiadomości oznaczone Do odpowiedzi: {stats['reply']}.")
    if stats['urgent']: advice.append(f"Sprawdź wiadomości oznaczone jako pilne: {stats['urgent']}.")
    if stats['payment']: advice.append(f"Sprawdź wiadomości oznaczone Do zapłaty: {stats['payment']}.")
    if stats['categories']['uncategorized']:
        advice.append(f"Uzupełnij kategorie wiadomości bez oznaczenia: {stats['categories']['uncategorized']}.")
    return {'summary': f"Odebrane: {stats['received']}. Wysłane: {stats['sent']}. "
            f"Oznaczony spam: {stats['spam']}. Od przypisanych firm: {stats['clients']}. "
            f"Reklamy: {stats['categories']['advertisement']}. Faktury: {stats['categories']['invoice']}. "
            f"Pilne: {stats['urgent']}. Do odpowiedzi: {stats['reply']}. Do zapłaty: {stats['payment']}. "
            f"Informacje: {stats['info']}. Nieprzeczytane: {stats['unread']}.", 'recommendations': advice}


def install(app, db, user, now):
    @app.get('/api/client-mail/day-report')
    def report(day: date | None = None, current=Depends(user)):
        day = day or datetime.now(WARSAW).date()
        with db() as con: return {**statistics(con, current['id'], day), 'generated_at': now()}

    @app.post('/api/client-mail/day-report')
    def analyze(body: DayRequest, current=Depends(user)):
        with db() as con: return {**statistics(con, current['id'], body.day), 'generated_at': now()}
