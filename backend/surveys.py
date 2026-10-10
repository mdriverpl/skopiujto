"""Assigned surveys with immutable questions and one response per recipient."""
import json
import math
import secrets
import hashlib
import time
from datetime import date
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, StrictBool, StrictStr, model_validator
from email_validator import validate_email, EmailNotValidError
from backend import mailer, sms, survey_scoring

SCHEMA = '''
CREATE TABLE IF NOT EXISTS surveys(
 id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id),
 title TEXT NOT NULL,description TEXT NOT NULL,questions TEXT NOT NULL,
 created_at TEXT NOT NULL,closed_at TEXT);
CREATE TABLE IF NOT EXISTS survey_recipients(
 survey_id TEXT NOT NULL REFERENCES surveys(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,
 answers TEXT,submitted_at TEXT,PRIMARY KEY(survey_id,user_id));
CREATE INDEX IF NOT EXISTS survey_recipient_user ON survey_recipients(user_id);
CREATE TABLE IF NOT EXISTS survey_dispatches(
 survey_id TEXT NOT NULL REFERENCES surveys(id),request_id TEXT NOT NULL,created_at TEXT NOT NULL,
 PRIMARY KEY(survey_id,request_id));
CREATE TABLE IF NOT EXISTS survey_invites(
 id TEXT PRIMARY KEY,survey_id TEXT NOT NULL REFERENCES surveys(id),request_id TEXT NOT NULL,
 name TEXT NOT NULL,channel TEXT NOT NULL,address TEXT NOT NULL,token_hash TEXT UNIQUE NOT NULL,
 expires DOUBLE PRECISION NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',sent_at TEXT,
 answers TEXT,submitted_at TEXT,UNIQUE(survey_id,channel,address));
CREATE INDEX IF NOT EXISTS survey_invite_parent ON survey_invites(survey_id);
CREATE TABLE IF NOT EXISTS survey_interpretations(
 survey_id TEXT PRIMARY KEY REFERENCES surveys(id) ON DELETE CASCADE,
 data TEXT NOT NULL,fingerprint TEXT NOT NULL,created_at TEXT NOT NULL);
'''

class Question(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    label: str = Field(min_length=1, max_length=200)
    type: Literal['text', 'textarea', 'number', 'date', 'select', 'checkbox'] = 'text'
    required: bool = True
    options: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def validate_question(self):
        self.label = self.label.strip()
        if not self.label: raise ValueError('Podaj nazwę pola.')
        self.options = [value.strip() for value in self.options]
        if any(not value or len(value) > 200 for value in self.options): raise ValueError('Podaj poprawne opcje odpowiedzi.')
        if len(set(self.options)) != len(self.options): raise ValueError('Opcje odpowiedzi nie mogą się powtarzać.')
        if self.type == 'select' and len(self.options) < 2: raise ValueError('Dodaj co najmniej dwie opcje wyboru.')
        if self.type != 'select' and self.options: raise ValueError('Opcje dotyczą tylko listy wyboru.')
        return self

class SurveyInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=5000)
    questions: list[Question] = Field(min_length=1, max_length=40)
    recipients: list[str] = Field(default_factory=list, max_length=200)
    scoring_profile: Literal['', 'phq9'] = ''

    @model_validator(mode='after')
    def validate_survey(self):
        self.title = self.title.strip()
        if not self.title: raise ValueError('Podaj tytuł ankiety.')
        if len({item.id for item in self.questions}) != len(self.questions): raise ValueError('Pola ankiety muszą mieć różne identyfikatory.')
        if self.scoring_profile == 'phq9':
            preset = survey_scoring.phq9_preset()
            if [q.model_dump() for q in self.questions] != preset['questions']:
                raise ValueError('PHQ-9 wymaga oryginalnych 9 pytań i stałych opcji odpowiedzi.')
            self.description = preset['description']
        return self

class InterpretationInput(BaseModel):
    prompt: StrictStr = Field(default='', max_length=8000)
    grading: StrictBool = False

    @model_validator(mode='after')
    def grading_prompt(self):
        if self.grading and not self.prompt.strip():
            raise ValueError('Podaj w prompcie kryteria i skalę oceny ankiety.')
        return self


class BatchInterpretationInput(InterpretationInput):
    survey_ids: list[StrictStr] = Field(min_length=1, max_length=10)


class ResponseInput(BaseModel):
    answers: dict[str, StrictStr | StrictBool] = Field(max_length=40)

class InviteInput(BaseModel):
    name: str = Field(default='', max_length=200)
    channel: Literal['email', 'sms']
    address: str = Field(min_length=1, max_length=320)

    @model_validator(mode='after')
    def valid_address(self):
        self.name = self.name.strip()
        try:
            self.address = (validate_email(self.address.strip(), check_deliverability=False, allow_smtputf8=False).ascii_email
                            if self.channel == 'email' else sms.phone_number(self.address))
        except (EmailNotValidError, ValueError): raise ValueError('Podaj poprawny adres e-mail lub numer telefonu.') from None
        return self

class DispatchInput(BaseModel):
    request_id: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    recipients: list[InviteInput] = Field(min_length=1, max_length=100)
    days: int = Field(default=14, strict=True, ge=1, le=90)

def validated_answers(questions, values):
    if set(values) - {q['id'] for q in questions}: raise HTTPException(422, 'Odpowiedź zawiera nieznane pole.')
    result = {}
    for q in questions:
        value = values.get(q['id'], False if q['type'] == 'checkbox' else '')
        if q['type'] == 'checkbox':
            if type(value) is not bool: raise HTTPException(422, f"Pole „{q['label']}” wymaga zaznaczenia lub odznaczenia.")
            if q['required'] and not value: raise HTTPException(422, f"Zaznacz pole „{q['label']}”.")
        else:
            if not isinstance(value, str): raise HTTPException(422, 'Nieprawidłowy typ odpowiedzi.')
            value = value.strip()
            if len(value) > 5000: raise HTTPException(422, 'Odpowiedź jest za długa.')
            if q['required'] and not value: raise HTTPException(422, f"Uzupełnij pole „{q['label']}”.")
            if value:
                if q['type'] == 'select' and value not in q['options']: raise HTTPException(422, 'Wybierz odpowiedź z listy.')
                if q['type'] == 'date':
                    try:
                        if date.fromisoformat(value).isoformat() != value: raise ValueError()
                    except ValueError: raise HTTPException(422, 'Podaj poprawną datę.') from None
                if q['type'] == 'number':
                    try:
                        if not math.isfinite(float(value)): raise ValueError()
                    except (ValueError, OverflowError): raise HTTPException(422, 'Podaj poprawną liczbę.') from None
        result[q['id']] = value
    return result

def install(app, db, user, now):
    from backend import ai

    def analysis_data(con, row, current):
        counts = summary(con, row, current)
        answers = [json.loads(item['answers']) for item in con.execute('''
            SELECT answers FROM survey_recipients WHERE survey_id=? AND submitted_at IS NOT NULL
            UNION ALL
            SELECT answers FROM survey_invites WHERE survey_id=? AND submitted_at IS NOT NULL''',
            (row['id'], row['id']))]
        answers.sort(key=lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False))
        data = {'title': row['title'], 'description': row['description'],
                'questions': json.loads(row['questions']), 'expected': counts['expected'],
                'completed': len(answers), 'answers': answers, 'scoring_profile': row['scoring_profile']}
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return data, fingerprint

    def accessible(con, identifier, current):
        row = con.execute('''SELECT s.*,u.name AS owner_name FROM surveys s JOIN users u ON u.id=s.owner_id
          WHERE s.id=? AND (s.owner_id=? OR EXISTS(SELECT 1 FROM survey_recipients r WHERE r.survey_id=s.id AND r.user_id=?))''',
          (identifier, current['id'], current['id'])).fetchone()
        if not row: raise HTTPException(404, 'Nie znaleziono ankiety.')
        return row

    def summary(con, row, current):
        own = con.execute('SELECT submitted_at FROM survey_recipients WHERE survey_id=? AND user_id=?', (row['id'], current['id'])).fetchone()
        counts = con.execute('SELECT count(*) AS expected,count(submitted_at) AS completed FROM survey_recipients WHERE survey_id=?', (row['id'],)).fetchone()
        external = con.execute('SELECT count(*) AS expected,count(submitted_at) AS completed FROM survey_invites WHERE survey_id=?', (row['id'],)).fetchone()
        return {key: row[key] for key in ('id', 'title', 'description', 'created_at', 'closed_at', 'owner_name')} | {
            'is_owner': row['owner_id'] == current['id'], 'assigned': own is not None,
            'submitted_at': own['submitted_at'] if own else None, 'expected': counts['expected'] + external['expected'], 'completed': counts['completed'] + external['completed'],
            'question_count': len(json.loads(row['questions'])), 'scoring_profile': row['scoring_profile']}

    @app.get('/api/surveys/presets/phq9')
    def phq9_preset(current=Depends(user)):
        return survey_scoring.phq9_preset()

    @app.get('/api/surveys/recipients')
    def recipients(current=Depends(user)):
        with db() as con: return [dict(row) for row in con.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name,id')]

    @app.get('/api/surveys')
    def listing(current=Depends(user)):
        with db() as con:
            rows = con.execute('''SELECT s.*,u.name AS owner_name FROM surveys s JOIN users u ON u.id=s.owner_id
              WHERE s.owner_id=? OR EXISTS(SELECT 1 FROM survey_recipients r WHERE r.survey_id=s.id AND r.user_id=?)
              ORDER BY s.created_at DESC,s.id''', (current['id'], current['id'])).fetchall()
            return [summary(con, row, current) for row in rows]

    @app.post('/api/surveys', status_code=201)
    def create(body: SurveyInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            people = []
            for identifier in dict.fromkeys(body.recipients):
                person = con.execute('SELECT id,name FROM users WHERE id=? AND active=1', (identifier,)).fetchone()
                if not person: raise HTTPException(422, 'Wybrany odbiorca nie istnieje lub jest nieaktywny.')
                people.append(person)
            identifier, timestamp = secrets.token_hex(16), now()
            con.execute('INSERT INTO surveys(id,owner_id,title,description,questions,created_at,scoring_profile) VALUES(?,?,?,?,?,?,?)',
                (identifier, current['id'], body.title, body.description.strip(), json.dumps([q.model_dump() for q in body.questions], ensure_ascii=False), timestamp, body.scoring_profile))
            for person in people:
                con.execute('INSERT INTO survey_recipients(survey_id,user_id,name) VALUES(?,?,?)', (identifier, person['id'], person['name']))
                con.execute('INSERT INTO user_messages(id,sender_id,recipient_id,subject,message,created_at) VALUES(?,?,?,?,?,?)',
                    (secrets.token_hex(16), current['id'], person['id'], ('Ankieta: ' + body.title)[:200],
                     'Masz nową ankietę do wypełnienia: ' + body.title + '. Otwórz zakładkę Ankiety → Dla mnie.\n\n' + body.description.strip(), timestamp))
            return summary(con, accessible(con, identifier, current), current)

    @app.get('/api/surveys/{identifier}')
    def details(identifier: str, current=Depends(user)):
        with db() as con:
            row = accessible(con, identifier, current)
            interpretation = None
            if row['owner_id'] == current['id']:
                saved = con.execute('SELECT * FROM survey_interpretations WHERE survey_id=?', (identifier,)).fetchone()
                if saved:
                    _, fingerprint = analysis_data(con, row, current)
                    interpretation = {**json.loads(saved['data']), 'created_at': saved['created_at'],
                                      'stale': saved['fingerprint'] != fingerprint}
            people = con.execute('SELECT user_id,name,answers,submitted_at FROM survey_recipients WHERE survey_id=? ORDER BY name,user_id', (identifier,)).fetchall()
            result = {**summary(con, row, current), 'scoring_profile': row['scoring_profile'], 'interpretation': interpretation, 'questions': json.loads(row['questions']), 'responses': [
                {'user_id': p['user_id'], 'name': p['name'], 'is_me': p['user_id'] == current['id'], 'sent_at': row['created_at'], 'answers': json.loads(p['answers']) if p['answers'] else None, 'submitted_at': p['submitted_at']}
                for p in people if row['owner_id'] == current['id'] or p['user_id'] == current['id']] + ([
                {'user_id': 'invite:' + p['id'], 'name': p['name'] or p['address'], 'is_me': False,
                 'channel': p['channel'], 'address': p['address'], 'status': p['status'], 'reason': p['reason'], 'sent_at': p['sent_at'],
                 'submitted_at': p['submitted_at'], 'answers': json.loads(p['answers']) if p['answers'] else None}
                for p in con.execute('SELECT * FROM survey_invites WHERE survey_id=? ORDER BY name,address', (identifier,))]
                if row['owner_id'] == current['id'] else [])}
            for response in result['responses']:
                response['result'] = survey_scoring.score(row['scoring_profile'], response['answers']) if response['submitted_at'] else None
            own = next((response for response in result['responses'] if response['is_me']), None)
            result['result'] = own['result'] if own else None
            return result

    def interpretation_source(identifier, current):
        with db() as con:
            row = accessible(con, identifier, current)
            if row['owner_id'] != current['id']:
                raise HTTPException(403, 'Tylko autor może interpretować wyniki ankiety.')
            data, fingerprint = analysis_data(con, row, current)
        if not data['completed']:
            raise HTTPException(422, 'Interpretacja wymaga co najmniej jednej przesłanej odpowiedzi.')
        if len(json.dumps(data, ensure_ascii=False).encode()) > 200000:
            raise HTTPException(422, 'Wyniki są zbyt obszerne do interpretacji AI.')
        return data, fingerprint

    async def save_interpretation(identifier, current, data, fingerprint, prompt, grading=False):
        result = await ai.interpret_survey(data, prompt, grading)
        timestamp = now()
        report = {**result, 'completed': data['completed'], 'expected': data['expected'], 'prompt': prompt, 'grading': grading}
        with db() as con:
            con.begin_write()
            row = accessible(con, identifier, current)
            _, latest = analysis_data(con, row, current)
            con.execute('''INSERT INTO survey_interpretations(survey_id,data,fingerprint,created_at) VALUES(?,?,?,?)
                ON CONFLICT(survey_id) DO UPDATE SET data=excluded.data,fingerprint=excluded.fingerprint,created_at=excluded.created_at''',
                (identifier, json.dumps(report, ensure_ascii=False), fingerprint, timestamp))
        return {**report, 'created_at': timestamp, 'stale': latest != fingerprint}

    @app.post('/api/surveys/{identifier}/interpretation')
    async def interpret(identifier: str, body: InterpretationInput | None = None, current=Depends(user)):
        prompt = body.prompt.strip() if body else ''
        data, fingerprint = interpretation_source(identifier, current)
        if body and body.grading and data['scoring_profile']:
            raise HTTPException(422, 'PHQ-9 ma stały klucz punktacji; ocena z promptu nie jest dostępna.')
        if current['id'] in ai.requests:
            raise HTTPException(429, 'Poczekaj na zakończenie poprzedniego generowania.')
        ai.requests.add(current['id'])
        try:
            return await save_interpretation(identifier, current, data, fingerprint, prompt, body.grading if body else False)
        finally:
            ai.requests.discard(current['id'])

    @app.post('/api/surveys/interpretation')
    async def interpret_batch(body: BatchInterpretationInput, current=Depends(user)):
        identifiers = list(dict.fromkeys(body.survey_ids))
        sources = [(identifier, *interpretation_source(identifier, current)) for identifier in identifiers]
        if body.grading and any(data['scoring_profile'] for _, data, _ in sources):
            raise HTTPException(422, 'PHQ-9 ma stały klucz punktacji; wyłącz ocenę z promptu dla tej analizy.')
        if current['id'] in ai.requests:
            raise HTTPException(429, 'Poczekaj na zakończenie poprzedniego generowania.')
        ai.requests.add(current['id'])
        try:
            prompt = body.prompt.strip()
            reports = []
            for identifier, data, fingerprint in sources:
                report = await save_interpretation(identifier, current, data, fingerprint, prompt, body.grading)
                reports.append({'id': identifier, 'title': data['title'], **report})
            summary_report = await ai.summarize_surveys(reports, prompt)
            return {'surveys': reports, 'summary': summary_report, 'prompt': prompt, 'grading': body.grading, 'created_at': now()}
        finally:
            ai.requests.discard(current['id'])

    def dispatch_result(con, identifier, request_id):
        return {'recipients': [dict(row) for row in con.execute(
            'SELECT id,name,channel,address,status,reason,sent_at FROM survey_invites WHERE survey_id=? AND request_id=?', (identifier, request_id))]}

    @app.post('/api/surveys/{identifier}/send')
    def send(identifier: str, body: DispatchInput, current=Depends(user)):
        with db() as con:
            row = accessible(con, identifier, current)
            if row['owner_id'] != current['id']: raise HTTPException(403, 'Tylko autor może wysłać ankietę.')
            if con.execute('SELECT 1 FROM survey_dispatches WHERE survey_id=? AND request_id=?', (identifier, body.request_id)).fetchone():
                return dispatch_result(con, identifier, body.request_id)
        configs = {channel: mailer.configuration() if channel == 'email' else sms.configuration() for channel in {p.channel for p in body.recipients}}
        work = []
        with db() as con:
            con.begin_write()
            row = accessible(con, identifier, current)
            if row['closed_at']: raise HTTPException(409, 'Ankieta jest zamknięta.')
            if con.execute('SELECT 1 FROM survey_dispatches WHERE survey_id=? AND request_id=?', (identifier, body.request_id)).fetchone():
                return dispatch_result(con, identifier, body.request_id)
            seen = set()
            for person in body.recipients:
                key = (person.channel, person.address)
                if key in seen: continue
                seen.add(key)
                if con.execute('SELECT 1 FROM survey_invites WHERE survey_id=? AND channel=? AND address=?', (identifier, *key)).fetchone(): continue
                token, invite_id = secrets.token_urlsafe(32), secrets.token_hex(16)
                link = configs[person.channel]['public_url'] + '/survey/' + token
                text = 'Ankieta: ' + row['title'] + '\n' + link + f'\nLink ważny {body.days} dni.'
                if person.channel == 'sms' and len(text) > 1200: raise HTTPException(422, 'Adres aplikacji jest za długi do wysyłki SMS.')
                con.execute('INSERT INTO survey_invites(id,survey_id,request_id,name,channel,address,token_hash,expires,status) VALUES(?,?,?,?,?,?,?,?,?)',
                    (invite_id, identifier, body.request_id, person.name, person.channel, person.address,
                     hashlib.sha256(token.encode()).hexdigest(), time.time() + body.days * 86400, 'sending'))
                work.append((invite_id, person, text))
            if not work: raise HTTPException(409, 'Wybrani odbiorcy są już przypisani do tej ankiety. Sprawdź odpowiedzi i statusy wysyłki.')
            con.execute('INSERT INTO survey_dispatches(survey_id,request_id,created_at) VALUES(?,?,?)', (identifier, body.request_id, now()))
        for invite_id, person, text in work:
            status, reason, sent_at = 'sent', '', None
            try:
                if person.channel == 'email': mailer.send_message(configs['email'], person.address, current['name'], ('Ankieta: ' + row['title'])[:200], text)
                else: sms.send_text(configs['sms'], person.address, text)
                sent_at = now()
            except HTTPException as exc: status, reason = 'failed', str(exc.detail)
            except Exception: status, reason = 'failed', 'Niepotwierdzona wysyłka. Sprawdź dostawcę przed kolejną próbą.'
            with db() as con: con.execute('UPDATE survey_invites SET status=?,reason=?,sent_at=? WHERE id=?', (status, reason, sent_at, invite_id))
        with db() as con: return dispatch_result(con, identifier, body.request_id)

    def token_invite(con, token):
        if len(token) > 100: raise HTTPException(404, 'Nie znaleziono zaproszenia.')
        invite = con.execute('SELECT * FROM survey_invites WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not invite or invite['status'] not in ('sent', 'sending'): raise HTTPException(404, 'Nie znaleziono zaproszenia.')
        if invite['expires'] < time.time(): raise HTTPException(410, 'Link do ankiety wygasł.')
        return invite

    @app.get('/api/survey-links/{token}')
    def public_survey(token: str):
        with db() as con:
            invite = token_invite(con, token)
            row = con.execute('SELECT * FROM surveys WHERE id=?', (invite['survey_id'],)).fetchone()
            saved_answers = json.loads(invite['answers']) if invite['answers'] else None
            return {key: row[key] for key in ('title', 'description', 'closed_at', 'scoring_profile')} | {
                'questions': json.loads(row['questions']), 'submitted_at': invite['submitted_at'],
                'answers': saved_answers, 'result': survey_scoring.score(row['scoring_profile'], saved_answers) if invite['submitted_at'] else None}

    @app.post('/api/survey-links/{token}/responses')
    def public_submit(token: str, body: ResponseInput):
        with db() as con:
            con.begin_write()
            invite = token_invite(con, token)
            row = con.execute('SELECT * FROM surveys WHERE id=?', (invite['survey_id'],)).fetchone()
            if row['closed_at']: raise HTTPException(409, 'Ankieta jest zamknięta.')
            if invite['submitted_at']: raise HTTPException(409, 'Odpowiedź została już wysłana.')
            answers = validated_answers(json.loads(row['questions']), body.answers)
            timestamp = now()
            con.execute('UPDATE survey_invites SET answers=?,submitted_at=? WHERE id=?', (json.dumps(answers, ensure_ascii=False), timestamp, invite['id']))
            return {'submitted_at': timestamp, 'result': survey_scoring.score(row['scoring_profile'], answers)}

    @app.post('/api/surveys/{identifier}/responses')
    def submit(identifier: str, body: ResponseInput, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = accessible(con, identifier, current)
            recipient = con.execute('SELECT submitted_at FROM survey_recipients WHERE survey_id=? AND user_id=?', (identifier, current['id'])).fetchone()
            if not recipient: raise HTTPException(403, 'Nie jesteś odbiorcą tej ankiety.')
            if row['closed_at']: raise HTTPException(409, 'Ankieta jest zamknięta.')
            if recipient['submitted_at']: raise HTTPException(409, 'Odpowiedź została już wysłana.')
            answers = validated_answers(json.loads(row['questions']), body.answers)
            timestamp = now()
            con.execute('UPDATE survey_recipients SET answers=?,submitted_at=? WHERE survey_id=? AND user_id=?',
                (json.dumps(answers, ensure_ascii=False), timestamp, identifier, current['id']))
            return {'submitted_at': timestamp, 'result': survey_scoring.score(row['scoring_profile'], answers)}

    @app.delete('/api/surveys/{identifier}')
    def delete(identifier: str, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = accessible(con, identifier, current)
            if row['owner_id'] != current['id']: raise HTTPException(403, 'Tylko autor może usunąć ankietę.')
            con.execute('DELETE FROM survey_invites WHERE survey_id=?', (identifier,))
            con.execute('DELETE FROM survey_dispatches WHERE survey_id=?', (identifier,))
            con.execute('DELETE FROM surveys WHERE id=?', (identifier,))
            return {'ok': True}

    @app.post('/api/surveys/{identifier}/close')
    def close(identifier: str, current=Depends(user)):
        with db() as con:
            con.begin_write()
            row = accessible(con, identifier, current)
            if row['owner_id'] != current['id']: raise HTTPException(403, 'Tylko autor może zamknąć ankietę.')
            con.execute('UPDATE surveys SET closed_at=coalesce(closed_at,?) WHERE id=?', (now(), identifier))
            return summary(con, accessible(con, identifier, current), current)
