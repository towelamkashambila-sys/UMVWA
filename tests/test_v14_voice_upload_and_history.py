from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
import app.db as db

ORIGINAL=db.DB_PATH

def test_voice_binary_upload_is_authenticated_scoped_and_retrievable():
    db.DB_PATH=Path('/tmp/umvwa_v14_voice.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass
    with TestClient(app) as client:
        login=client.post('/api/auth/login',json={'username':'person_sarah','password':'demo-sarah'}).json()
        h={'Authorization':'Bearer '+login['token'],'Content-Type':'audio/webm'}
        r=client.post('/api/voice-notes/upload?title=Morning%20brief',headers=h,content=b'RIFF-DEMO-AUDIO')
        assert r.status_code==200, r.text
        body=r.json()
        assert body['transcription_status']=='PENDING_PROVIDER'
        assert body['bytes']==len(b'RIFF-DEMO-AUDIO')
        audio=client.get('/api/voice-notes/'+body['id']+'/audio',headers={'Authorization':'Bearer '+login['token']})
        assert audio.status_code==200
        assert audio.content==b'RIFF-DEMO-AUDIO'
        bad=client.post('/api/voice-notes/upload?title=Bad',headers={'Authorization':'Bearer '+login['token'],'Content-Type':'application/octet-stream'},content=b'x')
        assert bad.status_code==415
    db.DB_PATH=ORIGINAL

def test_graph_mutations_record_authenticated_actor():
    db.DB_PATH=Path('/tmp/umvwa_v14_actor.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass
    with TestClient(app) as client:
        login=client.post('/api/auth/login',json={'username':'person_david','password':'demo-david'}).json()
        h={'Authorization':'Bearer '+login['token']}
        assert client.post('/api/meetings',headers=h,json={'title':'Client meeting','starts_at':'2026-09-04T11:00:00+00:00','thread_id':'thread_abc'}).status_code==200
        assert client.post('/api/artifacts',headers=h,json={'name':'Brief','source':'workspace','thread_id':'thread_abc'}).status_code==200
        with db.connect() as c:
            rows=c.execute("SELECT actor_id FROM history WHERE organization_id='org_demo' ORDER BY occurred_at,id").fetchall()
            assert any(r['actor_id']=='person_david' for r in rows)
    db.DB_PATH=ORIGINAL
