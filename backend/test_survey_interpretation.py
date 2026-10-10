import json

import pytest

from backend.test_storage import app_client
from backend.test_ai import provider, output
from backend.test_access import ADMIN, READER, create_reader, login


REPORT = {'summary': 'Przeważają pozytywne oceny.', 'findings': ['Jedna dobra ocena.'],
          'recommendations': ['Zbierz więcej odpowiedzi.'], 'limitations': ['Mała próba.'], 'grade': None}


def survey(client, recipients):
    return client.post('/api/surveys', json={'title': 'Ocena obsługi', 'questions': [
        {'id': 'q', 'label': 'Ocena', 'type': 'select', 'options': ['Dobra', 'Zła']},
        {'id': 'check', 'label': 'Kontakt', 'type': 'checkbox', 'required': False},
        {'id': 'text', 'label': 'Uwagi', 'type': 'textarea', 'required': False}],
        'recipients': recipients}).json()['id']


def answer(client, identifier, value='Dobra'):
    response = client.post(f'/api/surveys/{identifier}/responses', json={'answers': {
        'q': value, 'check': False, 'text': ''}})
    assert response.status_code == 200, response.text


def test_interpretation_includes_only_submitted_internal_and_external_answers(app_client, provider):
    main, client = app_client
    calls, result = provider
    result['json'] = output(REPORT)
    owner = client.get('/api/me').json()['id']
    reader = create_reader(client)
    identifier = survey(client, [owner, reader['id']])
    answer(client, identifier)
    with main.db() as con:
        con.execute('''INSERT INTO survey_invites(id,survey_id,request_id,name,channel,address,token_hash,
            expires,status,answers,submitted_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
            ('external', identifier, 'request_external', 'Private Name', 'email', 'private@example.com',
             'private-token-hash', 9999999999, 'sent', json.dumps({'q': 'Zła', 'check': False, 'text': 'Wolna obsługa'}), main.now()))
    response = client.post(f'/api/surveys/{identifier}/interpretation')
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['completed'] == 2 and report['expected'] == 3
    assert report['stale'] is False and report['summary'] == REPORT['summary']
    assert client.get(f'/api/surveys/{identifier}').json()['interpretation'] == report
    payload = json.loads(calls[0].content)
    data = json.loads(payload['input'])
    assert data['completed'] == 2 and len(data['answers']) == 2
    assert all(row['check'] is False for row in data['answers'])
    assert 'Private Name' not in payload['input'] and 'private@example.com' not in payload['input']
    assert 'private-token-hash' not in payload['input'] and owner not in payload['input']
    assert payload['store'] is False
    assert payload['text']['format']['name'] == 'survey_interpretation'
    login(client, READER)
    assert client.get(f'/api/surveys/{identifier}').json()['interpretation'] is None
    assert client.post(f'/api/surveys/{identifier}/interpretation').status_code == 403
    answer(client, identifier, 'Zła')
    login(client, ADMIN)
    assert client.get(f'/api/surveys/{identifier}').json()['interpretation']['stale'] is True
    assert client.post(f'/api/surveys/{identifier}/interpretation').json()['completed'] == 3
    assert client.get(f'/api/surveys/{identifier}').json()['interpretation']['stale'] is False


def test_no_answers_unknown_survey_and_logout_do_not_call_ai(app_client, provider):
    _, client = app_client
    calls, _ = provider
    identifier = survey(client, [])
    assert client.post(f'/api/surveys/{identifier}/interpretation').status_code == 422
    assert client.post('/api/surveys/missing/interpretation').status_code == 404
    client.post('/api/logout')
    assert client.post(f'/api/surveys/{identifier}/interpretation').status_code == 401
    assert calls == []


def test_custom_prompt_is_sent_to_provider_and_saved(app_client, provider):
    _, client = app_client
    calls, result = provider
    result['json'] = output(REPORT)
    identifier = survey(client, [client.get('/api/me').json()['id']])
    answer(client, identifier)
    response = client.post(f'/api/surveys/{identifier}/interpretation', json={'prompt': '  Skup się na obsłudze  '})
    assert response.status_code == 200, response.text
    assert response.json()['prompt'] == 'Skup się na obsłudze'
    assert client.get(f'/api/surveys/{identifier}').json()['interpretation']['prompt'] == 'Skup się na obsłudze'
    payload = json.loads(calls[0].content)
    assert json.loads(payload['input'])['analysis_prompt'] == 'Skup się na obsłudze'
    assert 'analysis_prompt' in payload['instructions']
    response = client.post(f'/api/surveys/{identifier}/interpretation', json={'prompt': ' '})
    assert response.status_code == 200 and response.json()['prompt'] == ''


def test_grade_uses_prompt_and_is_saved_with_justification(app_client, provider):
    _, client = app_client
    calls, result = provider
    grade = {'value': '4', 'scale': '1–5', 'criteria': 'Satysfakcja z obsługi', 'justification': 'Przesłano pozytywną ocenę obsługi.'}
    result['json'] = output({**REPORT, 'grade': grade})
    identifier = survey(client, [client.get('/api/me').json()['id']]); answer(client, identifier)
    prompt = 'Oceń satysfakcję z obsługi w skali 1–5 i uzasadnij ocenę.'
    response = client.post(f'/api/surveys/{identifier}/interpretation', json={'prompt': prompt, 'grading': True})
    assert response.status_code == 200, response.text
    assert response.json()['grade'] == grade and response.json()['grading'] is True
    assert client.get(f'/api/surveys/{identifier}').json()['interpretation']['grade'] == grade
    payload = json.loads(calls[0].content)
    assert json.loads(payload['input'])['analysis_prompt'] == prompt
    assert 'Nie wymyślaj skali ani kryteriów' in payload['instructions']
    assert 'grade' in payload['text']['format']['schema']['required']


def test_grading_requires_prompt_and_missing_grade_is_not_saved(app_client, provider):
    _, client = app_client
    calls, result = provider
    result['json'] = output(REPORT)
    identifier = survey(client, [client.get('/api/me').json()['id']]); answer(client, identifier)
    for path, body in [(f'/api/surveys/{identifier}/interpretation', {'grading': True}),
                       ('/api/surveys/interpretation', {'survey_ids': [identifier], 'grading': True, 'prompt': ' '})]:
        assert client.post(path, json=body).status_code == 422
    assert calls == []
    assert client.post(f'/api/surveys/{identifier}/interpretation', json={'grading': True, 'prompt': 'Skala 1–5'}).status_code == 502
    assert client.get(f'/api/surveys/{identifier}').json()['interpretation'] is None


def test_batch_grades_each_survey_and_leaves_combined_summary_ungraded(app_client, provider, monkeypatch):
    from backend import ai
    _, client = app_client
    calls, result = provider
    grade = {'value': 'Dobra', 'scale': 'Dobra/Zła', 'criteria': 'Ocena obsługi', 'justification': 'Pozytywna odpowiedź.'}
    result['json'] = output({**REPORT, 'grade': grade})
    seen = []
    async def summary(reports, prompt):
        seen.extend(reports)
        return REPORT
    monkeypatch.setattr(ai, 'summarize_surveys', summary)
    owner = client.get('/api/me').json()['id']
    identifiers = [survey(client, [owner]), survey(client, [owner])]
    for identifier in identifiers: answer(client, identifier)
    response = client.post('/api/surveys/interpretation', json={'survey_ids': identifiers, 'grading': True, 'prompt': 'Oceń obsługę w skali Dobra/Zła.'})
    assert response.status_code == 200, response.text
    assert all(report['grade'] == grade for report in response.json()['surveys'])
    assert response.json()['summary']['grade'] is None
    assert len(seen) == len(calls) == 2


def test_batch_analyzes_each_survey_separately_then_summarizes(app_client, provider):
    _, client = app_client
    calls, result = provider
    result['json'] = output(REPORT)
    owner = client.get('/api/me').json()['id']
    first, second = survey(client, [owner]), survey(client, [owner])
    answer(client, first, 'Dobra'); answer(client, second, 'Zła')
    response = client.post('/api/surveys/interpretation', json={'survey_ids': [second, first, second], 'prompt': 'Oceń obsługę'})
    assert response.status_code == 200, response.text
    report = response.json()
    assert [row['id'] for row in report['surveys']] == [second, first]
    assert report['summary'] == REPORT
    assert len(calls) == 3
    payloads = [json.loads(call.content) for call in calls]
    assert [p['text']['format']['name'] for p in payloads] == ['survey_interpretation', 'survey_interpretation', 'surveys_summary']
    assert json.loads(payloads[0]['input'])['answers'][0]['q'] == 'Zła'
    assert json.loads(payloads[1]['input'])['answers'][0]['q'] == 'Dobra'
    summary_data = json.loads(payloads[2]['input'])
    assert [row['id'] for row in summary_data['surveys']] == [second, first]
    assert summary_data['analysis_prompt'] == 'Oceń obsługę'
    for identifier in (first, second):
        assert client.get(f'/api/surveys/{identifier}').json()['interpretation']['prompt'] == 'Oceń obsługę'


def test_batch_validates_all_selected_surveys_before_calling_ai(app_client, provider):
    _, client = app_client
    calls, _ = provider
    owner = client.get('/api/me').json()['id']
    identifier = survey(client, [owner]); answer(client, identifier)
    empty = survey(client, [])
    for ids in ([], [identifier, empty], [identifier, 'missing'], ['missing'] * 11):
        assert client.post('/api/surveys/interpretation', json={'survey_ids': ids}).status_code in (404, 422)
    reader = create_reader(client)
    assigned = survey(client, [owner, reader['id']]); answer(client, assigned)
    login(client, READER)
    assert client.post('/api/surveys/interpretation', json={'survey_ids': [assigned]}).status_code == 403
    assert calls == []


def test_failed_summary_retains_individual_analyses_and_releases_guard(app_client, provider, monkeypatch):
    from backend import ai
    from fastapi import HTTPException
    main, client = app_client
    calls, result = provider
    result['json'] = output(REPORT)
    identifier = survey(client, [client.get('/api/me').json()['id']]); answer(client, identifier)
    async def failure(*args, **kwargs):
        raise HTTPException(502, 'Błąd podsumowania')
    monkeypatch.setattr(ai, 'summarize_surveys', failure)
    assert client.post('/api/surveys/interpretation', json={'survey_ids': [identifier]}).status_code == 502
    assert client.get(f'/api/surveys/{identifier}').json()['interpretation']['summary'] == REPORT['summary']
    assert not main.ai_requests and len(calls) == 1


@pytest.mark.parametrize('prompt', ['x' * 8001, 42, None])
def test_invalid_prompt_does_not_call_provider(app_client, provider, prompt):
    _, client = app_client
    calls, _ = provider
    identifier = survey(client, [client.get('/api/me').json()['id']])
    answer(client, identifier)
    assert client.post(f'/api/surveys/{identifier}/interpretation', json={'prompt': prompt}).status_code == 422
    assert calls == []


def test_failure_preserves_saved_interpretation_and_releases_busy_guard(app_client, provider):
    main, client = app_client
    calls, result = provider
    owner = client.get('/api/me').json()['id']
    identifier = survey(client, [owner])
    answer(client, identifier)
    result['json'] = output(REPORT)
    before = client.post(f'/api/surveys/{identifier}/interpretation').json()
    result['status'] = 429
    assert client.post(f'/api/surveys/{identifier}/interpretation').status_code == 503
    assert client.get(f'/api/surveys/{identifier}').json()['interpretation'] == before
    assert not main.ai_requests
    main.ai_requests.add(owner)
    try:
        assert client.post(f'/api/surveys/{identifier}/interpretation').status_code == 429
    finally:
        main.ai_requests.discard(owner)
    assert len(calls) == 2


@pytest.mark.parametrize('report', [{**REPORT, 'summary': ' '}, {**REPORT, 'findings': []},
                                  {**REPORT, 'limitations': ['']}, {'summary': 'Incomplete'}])
def test_invalid_interpretation_is_not_saved(app_client, provider, report):
    _, client = app_client
    _, result = provider
    owner = client.get('/api/me').json()['id']
    identifier = survey(client, [owner])
    answer(client, identifier)
    result['json'] = output(report)
    assert client.post(f'/api/surveys/{identifier}/interpretation').status_code == 502
    assert client.get(f'/api/surveys/{identifier}').json()['interpretation'] is None
