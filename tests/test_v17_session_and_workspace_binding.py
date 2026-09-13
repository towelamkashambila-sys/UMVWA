from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
import app.db as db

ORIGINAL=db.DB_PATH

def setup_function():
    db.DB_PATH=Path('/tmp/umvwa_v17.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass

def teardown_function():
    db.DB_PATH=ORIGINAL

def login(c,u,p):
    r=c.post('/api/auth/login',json={'username':u,'password':p})
    assert r.status_code==200
    return r.json()

def h(token): return {'Authorization':'Bearer '+token}

def test_authenticated_session_endpoint_is_source_of_identity():
    with TestClient(app) as c:
        d=login(c,'person_david','demo-david')
        r=c.get('/api/auth/session',headers=h(d['token']))
        assert r.status_code==200
        body=r.json()
        assert body['user_id']=='person_david'
        assert body['organization_id']=='org_demo'
        assert body['role']=='EXECUTIVE'
        assert 'password' not in body
        assert 'token' not in body

def test_voice_upload_honors_authenticated_workspace():
    with TestClient(app) as c:
        d=login(c,'person_david','demo-david')
        r=c.post('/api/voice-notes/upload?organization_id=not_org&title=bad',headers={**h(d['token']),'Content-Type':'audio/webm'},content=b'audio')
        assert r.status_code==403
