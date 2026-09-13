from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.db import DB_PATH

def test_api_authentication_and_role_boundaries():
    if DB_PATH.exists(): DB_PATH.unlink()
    with TestClient(app) as client:
        assert client.get('/api/health').status_code == 200
        assert client.get('/api/workspaces/org_demo').status_code == 401
        r=client.post('/api/auth/login',json={'username':'person_david','password':'demo-david'}); assert r.status_code==200
        david=r.json()['token']
        headers={'Authorization':'Bearer '+david}
        assert client.get('/api/workspaces/org_demo',headers=headers).status_code==200
        assert client.get('/api/executive/org_demo',headers=headers).status_code==200
        assert client.get('/api/assistant/org_demo/person_sarah',headers=headers).status_code==200
        r=client.post('/api/auth/login',json={'username':'person_sarah','password':'demo-sarah'}); assert r.status_code==200
        sarah=r.json()['token']; sh={'Authorization':'Bearer '+sarah}
        assert client.get('/api/executive/org_demo',headers=sh).status_code==403
        assert client.post('/api/capacity',headers=sh,json={'assistant_id':'person_sarah','state':'BUSY'}).status_code==200
        assert client.post('/api/capacity',headers=sh,json={'assistant_id':'person_david','state':'BUSY'}).status_code==403
