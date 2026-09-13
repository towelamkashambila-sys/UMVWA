from fastapi.testclient import TestClient
from app.main import app
from app.db import DB_PATH


def test_pilot_runtime_core_http_journey():
    if DB_PATH.exists():
        DB_PATH.unlink()
    with TestClient(app) as c:
        assert c.get('/api/health').status_code == 200
        assert c.get('/api/ready').status_code == 200
        login = c.post('/api/auth/login', json={'username':'person_david','password':'demo-david'})
        assert login.status_code == 200
        token = login.json()['token']
        h = {'Authorization': f'Bearer {token}'}
        assert c.get('/api/auth/session', headers=h).status_code == 200
        assert c.get('/api/executive/org_demo', headers=h).status_code == 200
        assert c.get('/api/preferences', headers=h).status_code == 200
        assert c.get('/api/workspace/configuration', headers=h).status_code == 200
        assert c.get('/api/workspaces/org_demo', headers=h).status_code == 200
        assert c.get('/api/work/org_demo/temporal', headers=h).status_code == 200
        assert c.get('/api/history/org_demo/out_demo', headers=h).status_code == 200
        assert c.post('/api/auth/logout', headers=h).status_code == 200
        assert c.get('/api/auth/session', headers=h).status_code == 401
