import os
from pathlib import Path
os.environ['UMVWA_SEED_DEMO']='1'
from fastapi.testclient import TestClient
from app.main import app
from app.db import DB_PATH

def test_personalization_is_bounded_and_persistent():
    if DB_PATH.exists(): DB_PATH.unlink()
    with TestClient(app) as c:
        d=c.post('/api/auth/login',json={'username':'person_david','password':'demo-david'}).json(); dh={'Authorization':'Bearer '+d['token']}
        s=c.post('/api/auth/login',json={'username':'person_sarah','password':'demo-sarah'}).json(); sh={'Authorization':'Bearer '+s['token']}
        r=c.patch('/api/preferences',json={'preferences':{'home_focus':['decisions','risk'],'timezone':'Africa/Lusaka'}},headers=sh); assert r.status_code==200
        assert c.get('/api/preferences',headers=sh).json()['preferences']['home_focus']==['decisions','risk']
        r=c.patch('/api/preferences',json={'preferences':{'lifecycle_state':'BROKEN_CANONICAL'}},headers=sh); assert r.status_code==400
        r=c.patch('/api/workspace/configuration',json={'configuration':{'default_workflow':['ACKNOWLEDGED','STARTED'],'work_terms':{'task':'work'}}},headers=dh); assert r.status_code==200
        assert c.get('/api/workspace/configuration',headers=sh).json()['configuration']['work_terms']['task']=='work'
        r=c.patch('/api/workspace/configuration',json={'configuration':{'approval_rules':{'finance':'EXECUTIVE'}}},headers=sh); assert r.status_code==403
        r=c.patch('/api/workspace/configuration',json={'configuration':{'lifecycle_definition':'override'}},headers=dh); assert r.status_code==400
