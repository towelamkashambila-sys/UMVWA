from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
import app.db as db

ORIGINAL=db.DB_PATH

def test_api_binds_communication_sender_and_context_owner_to_actor():
    db.DB_PATH=Path('/tmp/umvwa_v13_actor.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass
    with TestClient(app) as client:
        d=client.post('/api/auth/login',json={'username':'person_david','password':'demo-david'}).json()
        s=client.post('/api/auth/login',json={'username':'person_sarah','password':'demo-sarah'}).json()
        dh={'Authorization':'Bearer '+d['token']}; sh={'Authorization':'Bearer '+s['token']}
        assert client.post('/api/communications',headers=sh,json={'sender_id':'person_david','recipient_ids':['person_sarah'],'subject':'x','body':'y','thread_id':'thread_abc'}).status_code==403
        assert client.post('/api/communications',headers=sh,json={'sender_id':'person_sarah','recipient_ids':['person_david'],'subject':'x','body':'y','thread_id':'thread_abc'}).status_code==200
        assert client.post('/api/contexts',headers=sh,json={'title':'x','summary':'y','owner_id':'person_david'}).status_code==403
        assert client.post('/api/contexts',headers=sh,json={'title':'x','summary':'y'}).status_code==200
        assert client.post('/api/contexts',headers=dh,json={'title':'x','summary':'y','owner_id':'person_sarah'}).status_code==200
    db.DB_PATH=ORIGINAL
