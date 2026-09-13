from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi.testclient import TestClient
import app.db as db
from app.main import app

ORIGINAL=db.DB_PATH

def setup_function():
    db.DB_PATH=Path('/tmp/umvwa_v08.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass

def teardown_function(): db.DB_PATH=ORIGINAL

def login(client, username, password):
    token=client.post('/api/auth/login',json={'username':username,'password':password}).json()['token']
    return {'Authorization':'Bearer '+token}

def test_authenticated_actor_cannot_impersonate_another_member():
    with TestClient(app) as client:
        david=login(client,'person_david','demo-david')
        w=client.post('/api/work',json={'description':'Security test'},headers=david).json()
        r=client.post(f"/api/work/{w['id']}/transition/ACTIVE",json={'actor_id':'person_sarah'},headers=david)
        assert r.status_code==403

def test_history_and_temporal_projections_are_workspace_scoped_and_grounded():
    with TestClient(app) as client:
        david=login(client,'person_david','demo-david')
        due=(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat()
        w=client.post('/api/work',json={'description':'Temporal test','expected_completion':due},headers=david).json()['id']
        story=client.get(f'/api/history/org_demo/{w}',headers=david)
        assert story.status_code==200
        assert story.json()['history_count']>=1
        temporal=client.get('/api/work/org_demo/temporal?soon_hours=48',headers=david)
        assert temporal.status_code==200
        item=next(x for x in temporal.json()['work'] if x['id']==w)
        assert item['temporal_state']=='DUE_SOON'
        assert item['day']

def test_ask_returns_temporal_grounding_for_thread_work():
    with TestClient(app) as client:
        david=login(client,'person_david','demo-david')
        due=(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat()
        client.post('/api/work',json={'description':'Prepare ABC quotation','expected_completion':due},headers=david)
        r=client.post('/api/ask',json={'question':'What is happening with ABC?'},headers=david)
        assert r.status_code==200
        data=r.json()
        assert data['classification']=='GROUNDED'
        works=[x for x in data['sources'] if x['type']=='WorkItem']
        assert works and 'temporal_state' in works[0]
