from __future__ import annotations
import json
from .db import connect, utcnow_iso

ALLOWED_USER_KEYS = {'home_focus','notifications','meeting_prep','timezone','date_format'}
ALLOWED_ORG_KEYS = {'work_terms','approval_rules','default_workflow','priority_rules','notification_defaults'}

def _load(c, table, org, subject):
    row=c.execute(f'SELECT config FROM {table} WHERE organization_id=? AND subject_id=?',(org,subject)).fetchone()
    return json.loads(row['config']) if row else {}

def get_user_preferences(org, user):
    with connect() as c: return _load(c,'user_preferences',org,user)

def set_user_preferences(org,user,updates):
    clean={k:v for k,v in updates.items() if k in ALLOWED_USER_KEYS}
    if not clean: return get_user_preferences(org,user)
    with connect() as c:
        current=_load(c,'user_preferences',org,user); current.update(clean); now=utcnow_iso()
        c.execute('INSERT INTO user_preferences(organization_id,subject_id,config,updated_at) VALUES(?,?,?,?) ON CONFLICT(organization_id,subject_id) DO UPDATE SET config=excluded.config,updated_at=excluded.updated_at',(org,user,json.dumps(current,sort_keys=True),now))
        return current

def get_org_configuration(org):
    with connect() as c: return _load(c,'workspace_configuration',org,org)

def set_org_configuration(org,updates):
    clean={k:v for k,v in updates.items() if k in ALLOWED_ORG_KEYS}
    with connect() as c:
        current=_load(c,'workspace_configuration',org,org); current.update(clean); now=utcnow_iso()
        c.execute('INSERT INTO workspace_configuration(organization_id,subject_id,config,updated_at) VALUES(?,?,?,?) ON CONFLICT(organization_id,subject_id) DO UPDATE SET config=excluded.config,updated_at=excluded.updated_at',(org,org,json.dumps(current,sort_keys=True),now))
        return current
