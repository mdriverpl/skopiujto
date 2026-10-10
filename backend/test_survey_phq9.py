import hashlib
import time

import pytest

from backend import survey_scoring
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login


def answers(total):
    remaining = total
    result = {}
    for index in range(1, 10):
        points = min(remaining, 3); remaining -= points
        result[f'phq9_{index}'] = survey_scoring.OPTIONS[points]
    return result


@pytest.mark.parametrize('total', range(28))
def test_every_total_and_severity_boundary(total):
    result = survey_scoring.score('phq9', answers(total))
    expected = ['Objawy minimalne', 'Łagodne nasilenie objawów', 'Umiarkowane nasilenie objawów',
                'Umiarkowanie ciężkie nasilenie objawów', 'Ciężkie nasilenie objawów'][min(total // 5, 4)]
    assert result['total'] == total and result['maximum'] == 27
    assert result['severity'] == expected
    assert sum(item['points'] for item in result['items']) == total
    assert len(result['items']) == 9


def test_question_nine_flag_is_independent_of_total():
    values = answers(0); values['phq9_9'] = survey_scoring.OPTIONS[1]
    result = survey_scoring.score('phq9', values)
    assert result['total'] == 1 and result['follow_up_required'] is True
    assert survey_scoring.score('phq9', answers(24))['follow_up_required'] is False
    assert survey_scoring.score('', values) is None


def create_phq9(client, recipients):
    body = client.get('/api/surveys/presets/phq9').json()
    body['recipients'] = recipients
    response = client.post('/api/surveys', json=body)
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_individual_scores_persist_and_recipient_sees_only_their_result(app_client):
    main, client = app_client
    author = client.get('/api/me').json()['id']
    reader = create_reader(client)
    identifier = create_phq9(client, [author, reader['id']])
    response = client.post(f'/api/surveys/{identifier}/responses', json={'answers': answers(4)})
    assert response.status_code == 200 and response.json()['result']['total'] == 4
    login(client, READER)
    assert client.get(f'/api/surveys/{identifier}').json()['result'] is None
    response = client.post(f'/api/surveys/{identifier}/responses', json={'answers': answers(9)})
    assert response.status_code == 200 and response.json()['result']['total'] == 9
    detail = client.get(f'/api/surveys/{identifier}').json()
    assert detail['result']['total'] == 9 and len(detail['responses']) == 1
    assert detail['responses'][0]['result']['total'] == 9
    login(client, ADMIN)
    main.initialize()
    detail = client.get(f'/api/surveys/{identifier}').json()
    assert sorted(item['result']['total'] for item in detail['responses']) == [4, 9]
    assert client.post(f'/api/surveys/{identifier}/interpretation', json={'grading': True, 'prompt': 'Oceń w skali 1–5'}).status_code == 422


def test_public_results_are_token_specific_and_return_after_reload(app_client):
    main, client = app_client
    identifier = create_phq9(client, [])
    tokens = ['private-phq9-token-one', 'private-phq9-token-two']
    with main.db() as con:
        for index, token in enumerate(tokens):
            con.execute('''INSERT INTO survey_invites(id,survey_id,request_id,name,channel,address,token_hash,expires,status)
                VALUES(?,?,?,?,?,?,?,?,?)''', (f'invite_{index}', identifier, 'request_phq9', '', 'email',
                f'person{index}@example.com', hashlib.sha256(token.encode()).hexdigest(), time.time() + 3600, 'sent'))
    client.post('/api/logout')
    for token, total in zip(tokens, [0, 27]):
        response = client.post(f'/api/survey-links/{token}/responses', json={'answers': answers(total)})
        assert response.status_code == 200 and response.json()['result']['total'] == total
        detail = client.get(f'/api/survey-links/{token}').json()
        assert detail['result']['total'] == total and 'responses' not in detail
    assert client.get('/api/survey-links/unknown-phq9').status_code == 404


def test_phq9_questions_cannot_be_modified_and_all_answers_are_required(app_client):
    _, client = app_client
    body = client.get('/api/surveys/presets/phq9').json()
    body['questions'][0]['options'] = ['Tak', 'Nie']
    assert client.post('/api/surveys', json=body).status_code == 422
    identifier = create_phq9(client, [client.get('/api/me').json()['id']])
    incomplete = answers(0); incomplete.pop('phq9_9')
    assert client.post(f'/api/surveys/{identifier}/responses', json={'answers': incomplete}).status_code == 422
    invalid = answers(0); invalid['phq9_1'] = '4'
    assert client.post(f'/api/surveys/{identifier}/responses', json={'answers': invalid}).status_code == 422
    assert client.get(f'/api/surveys/{identifier}').json()['result'] is None
