from fastapi.testclient import TestClient
from app.main import app
import app.db as db
from pathlib import Path

ORIGINAL = db.DB_PATH

def setup_function():
    db.DB_PATH = Path('/tmp/umvwa_v19.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass

def teardown_function(): db.DB_PATH = ORIGINAL

def login(c, u='person_david', p='demo-david'):
    r=c.post('/api/auth/login', json={'username':u,'password':p})
    assert r.status_code==200
    return r.json()

def h(t): return {'Authorization':'Bearer '+t}

def test_logout_revokes_current_session():
    with TestClient(app) as c:
        d=login(c)
        assert c.get('/api/auth/session', headers=h(d['token'])).status_code==200
        r=c.post('/api/auth/logout', headers=h(d['token']))
        assert r.status_code==200 and r.json()['status']=='signed_out'
        assert c.get('/api/auth/session', headers=h(d['token'])).status_code==401

def test_logout_is_idempotent_at_client_boundary_but_requires_live_session():
    with TestClient(app) as c:
        d=login(c)
        assert c.post('/api/auth/logout', headers=h(d['token'])).status_code==200
        assert c.post('/api/auth/logout', headers=h(d['token'])).status_code==401

def test_executive_can_cleanup_expired_sessions():
    with TestClient(app) as c:
        d=login(c)
        r=c.post('/api/auth/cleanup', headers=h(d['token']))
        assert r.status_code==200 and 'removed' in r.json()

def test_assistant_cannot_run_session_cleanup():
    with TestClient(app) as c:
        d=login(c,'person_sarah','demo-sarah')
        assert c.post('/api/auth/cleanup', headers=h(d['token'])).status_code==403
