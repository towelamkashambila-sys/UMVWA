import os
from pathlib import Path
from datetime import datetime, timezone
os.environ['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'canonical_src')
from fastapi.testclient import TestClient
from app.main import app
from app.db import DB_PATH

def test_end_to_end_operational_journey():
    if DB_PATH.exists(): DB_PATH.unlink()
    with TestClient(app) as client:
        login=client.post('/api/auth/login',json={'username':'person_david','password':'demo-david'}).json(); headers={'Authorization':'Bearer '+login['token']}
        w=client.post('/api/work',json={'description':'Prepare ABC quotation for Friday meeting'},headers=headers).json()
        wid=w['id']
        sarah_login=client.post('/api/auth/login',json={'username':'person_sarah','password':'demo-sarah'}).json(); sarah_headers={'Authorization':'Bearer '+sarah_login['token']}
        for target,actor,actor_headers in [('ACTIVE','person_david',headers),('ACKNOWLEDGED','person_sarah',sarah_headers),('STARTED','person_sarah',sarah_headers),('WAITING','person_sarah',sarah_headers)]:
            r=client.post(f'/api/work/{wid}/transition/{target}',json={'actor_id':actor},headers=actor_headers); assert r.status_code==200,r.text
        # Human authority exists before On Hold; AI/recommendation cannot bypass it.
        auth=client.post('/api/authorities',json={'scope':'WORK_ITEM_ON_HOLD'},headers=headers); assert auth.status_code==200
        aid=auth.json()['id']
        r=client.post(f'/api/work/{wid}/transition/ON_HOLD',json={'actor_id':'person_david','authority':{'id':aid,'grantor_id':'person_david','recipient_id':'person_sarah','scope':'WORK_ITEM_ON_HOLD','effective_from':datetime.now(timezone.utc).isoformat()}},headers=headers)
        assert r.status_code==200,r.text
        r=client.post(f'/api/work/{wid}/transition/STARTED',json={'actor_id':'person_sarah'},headers=sarah_headers); assert r.status_code==200,r.text
        # Completion without canonical subject-linked evidence must fail.
        r=client.post(f'/api/work/{wid}/transition/COMPLETED',json={'actor_id':'person_sarah'},headers=sarah_headers); assert r.status_code==400
        ev={'id':'evidence_runtime_1','description':'Final quotation document attached','source':'document_upload','occurred_at':datetime.now(timezone.utc).isoformat()}
        r=client.post(f'/api/work/{wid}/transition/COMPLETED',json={'actor_id':'person_sarah','evidence':[ev]},headers=sarah_headers); assert r.status_code==200,r.text
        d=client.get('/api/work/'+wid,headers=sarah_headers).json()
        assert d['work']['lifecycle_state']=='COMPLETED'
        assert len(d['history'])==8

def test_role_surfaces_share_state_but_project_differently():
    with TestClient(app) as client:
        token=client.post('/api/auth/login',json={'username':'person_david','password':'demo-david'}).json()['token']; headers={'Authorization':'Bearer '+token}
        e=client.get('/api/executive/org_demo',headers=headers).json(); a=client.get('/api/assistant/org_demo/person_sarah',headers=headers).json()
        assert 'signals' in e and 'priority_work' in a
        assert 'operational_load' in a
