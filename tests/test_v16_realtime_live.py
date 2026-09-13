import json
from fastapi.testclient import TestClient
from app.main import app
import app.db as db
from pathlib import Path

ORIGINAL=db.DB_PATH

def setup_function():
    db.DB_PATH=Path('/tmp/umvwa_v16.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass

def teardown_function(): db.DB_PATH=ORIGINAL

def login(c,u,p):
    return {'Authorization':'Bearer '+c.post('/api/auth/login',json={'username':u,'password':p}).json()['token']}

def test_sse_cursor_replay_and_non_follow_mode():
    with TestClient(app) as c:
        david=login(c,'person_david','demo-david')
        w=c.post('/api/work',json={'description':'Live sync'},headers=david).json()['id']
        r=c.get('/api/events/org_demo/stream?follow=false',headers=david)
        assert r.status_code==200
        assert 'event: operational' in r.text
        assert w in r.text
        assert ': close' in r.text

def test_sse_rejects_workspace_without_membership():
    with TestClient(app) as c:
        r=c.get('/api/events/not_my_workspace/stream?follow=false',headers=login(c,'person_david','demo-david'))
        assert r.status_code in (401,403)
