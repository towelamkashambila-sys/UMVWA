from pathlib import Path
from fastapi.testclient import TestClient
import app.db as db
from app.main import app

ORIGINAL = db.DB_PATH

def setup_function():
    db.DB_PATH = Path('/tmp/umvwa_v21.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass

def teardown_function(): db.DB_PATH = ORIGINAL

def login(c,u='person_david',p='demo-david'):
    r=c.post('/api/auth/login',json={'username':u,'password':p}); assert r.status_code==200; return r.json()

def h(t): return {'Authorization':'Bearer '+t}

def test_ai_status_is_explicitly_safe_when_unconfigured():
    with TestClient(app) as c:
        d=login(c)
        r=c.get('/api/ai/status',headers=h(d['token']))
        assert r.status_code==200
        assert r.json()['human_control'] is True
        assert r.json()['configured'] is False

def test_privacy_export_is_self_scoped():
    with TestClient(app) as c:
        d=login(c,'person_sarah','demo-sarah')
        r=c.get('/api/privacy/export',headers=h(d['token']))
        assert r.status_code==200
        payload=r.json()
        assert payload['person']['id']=='person_sarah'
        assert 'password_hash' not in str(payload)

def test_privacy_policy_is_public_and_explicit():
    with TestClient(app) as c:
        r=c.get('/api/privacy/policy')
        assert r.status_code==200
        assert 'export' in r.json()

def test_backup_reports_checksum_and_nonzero_size():
    with TestClient(app) as c:
        d=login(c)
        r=c.post('/api/admin/backup',headers=h(d['token']))
        assert r.status_code==200
        body=r.json()
        assert body['bytes']>0 and len(body['sha256'])==64
        (db.BACKUP_ROOT/body['filename']).unlink()
