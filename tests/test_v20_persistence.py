from fastapi.testclient import TestClient
from app.main import app
import app.db as db
from pathlib import Path

ORIGINAL = db.DB_PATH

def setup_function():
    db.DB_PATH = Path('/tmp/umvwa_v20.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass

def teardown_function(): db.DB_PATH = ORIGINAL

def login(c,u='person_david',p='demo-david'):
    r=c.post('/api/auth/login',json={'username':u,'password':p}); assert r.status_code==200; return r.json()

def h(t): return {'Authorization':'Bearer '+t}

def test_ready_reports_database_integrity():
    with TestClient(app) as c:
        r=c.get('/api/ready'); assert r.status_code==200; assert r.json()['integrity']=='ok'

def test_executive_can_create_consistent_backup():
    with TestClient(app) as c:
        d=login(c)
        r=c.post('/api/admin/backup',headers=h(d['token']))
        assert r.status_code==200
        backup=db.BACKUP_ROOT/r.json()['filename']
        assert backup.is_file()
        backup.unlink()

def test_assistant_cannot_create_database_backup():
    with TestClient(app) as c:
        d=login(c,'person_sarah','demo-sarah')
        assert c.post('/api/admin/backup',headers=h(d['token'])).status_code==403
