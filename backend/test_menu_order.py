import json
import pytest
from fastapi.testclient import TestClient
from backend.test_storage import app_client
from backend.test_access import ADMIN, READER, create_reader, login


def test_menu_order_persists_on_account_across_sessions_and_initialization(app_client):
    main, client = app_client
    assert client.get('/api/me').json()['menu_order'] == []
    order = ['notes', 'documents', 'start', 'drive']
    response = client.put('/api/me/menu-order', json={'menu_order': order})
    assert response.status_code == 200 and response.json()['menu_order'] == order
    with main.db() as con:
        assert json.loads(con.execute('SELECT menu_order FROM users WHERE name=?', (ADMIN['name'],)).fetchone()[0]) == order
    main.initialize()
    with TestClient(main.app) as other_browser:
        assert other_browser.post('/api/login', json=ADMIN).json()['menu_order'] == order
        assert other_browser.get('/api/me').json()['menu_order'] == order


def test_menu_order_is_saved_only_for_the_authenticated_account(app_client):
    _, client = app_client
    client.put('/api/me/menu-order', json={'menu_order': ['documents', 'start']})
    create_reader(client)
    login(client, READER)
    assert client.get('/api/me').json()['menu_order'] == []
    assert client.put('/api/me/menu-order', json={'menu_order': ['notes', 'start']}).status_code == 200
    assert client.get('/api/me').json()['menu_order'] == ['notes', 'start']
    assert login(client, ADMIN)['menu_order'] == ['documents', 'start']
    client.post('/api/logout')
    assert client.put('/api/me/menu-order', json={'menu_order': ['start']}).status_code == 401


@pytest.mark.parametrize('order', [['unknown'], ['start', 'start'], ['start'] * 12, 'start', [123]])
def test_menu_order_rejects_invalid_input_without_changing_settings(app_client, order):
    _, client = app_client
    assert client.put('/api/me/menu-order', json={'menu_order': order}).status_code == 422
    assert client.get('/api/me').json()['menu_order'] == []
