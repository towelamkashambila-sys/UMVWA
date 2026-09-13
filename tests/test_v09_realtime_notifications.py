from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient
import app.db as db
from app.main import app

ORIGINAL=db.DB_PATH

def setup_function():
    db.DB_PATH=Path('/tmp/umvwa_v09.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass

def teardown_function(): db.DB_PATH=ORIGINAL

def login(client,u,p):
    return {'Authorization':'Bearer '+client.post('/api/auth/login',json={'username':u,'password':p}).json()['token']}

def test_transition_notification_is_private_and_readable():
    with TestClient(app) as c:
        david=login(c,'person_david','demo-david')
        sarah=login(c,'person_sarah','demo-sarah')
        w=c.post('/api/work',json={'description':'Notify Sarah'},headers=david).json()['id']
        r=c.post(f'/api/work/{w}/transition/ACTIVE',json={'actor_id':'person_david'},headers=david)
        assert r.status_code==200
        n=c.get('/api/notifications/org_demo?unread_only=true',headers=sarah)
        assert n.status_code==200 and n.json()['notifications']
        item=n.json()['notifications'][0]
        assert c.post(f"/api/notifications/{item['id']}/read",headers=sarah).status_code==200
        assert c.get('/api/notifications/org_demo?unread_only=true',headers=sarah).json()['notifications']==[]
        assert c.get('/api/notifications/org_demo',headers=david).json()['notifications']==[]

def test_voice_note_cannot_impersonate_author_and_event_is_single():
    with TestClient(app) as c:
        david=login(c,'person_david','demo-david')
        r=c.post('/api/voice-notes',json={'author_id':'person_sarah','title':'forged'},headers=david)
        assert r.status_code==403
        ok=c.post('/api/voice-notes',json={'author_id':'person_david','title':'real','transcript':'hello'},headers=david)
        assert ok.status_code==200
        events=c.get('/api/events/org_demo',headers=david).json()['events']
        assert sum(e['event_type']=='VOICE_NOTE_CREATED' for e in events)==1

def test_sse_stream_is_workspace_scoped_and_contains_event():
    with TestClient(app) as c:
        david=login(c,'person_david','demo-david')
        w=c.post('/api/work',json={'description':'Realtime'},headers=david).json()['id']
        resp=c.get('/api/events/org_demo/stream?follow=false',headers=david)
        assert resp.status_code==200
        assert 'WORK_CREATED' in resp.text and w in resp.text
