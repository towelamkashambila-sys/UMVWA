import os
from pathlib import Path
os.environ['PYTHONPATH']=str(Path(__file__).resolve().parents[1]) + ':' + str(Path(__file__).resolve().parents[1]/'canonical_src')

def test_password_hash_roundtrip():
    from app.auth import hash_password, verify_password
    h = hash_password('secret')
    assert verify_password('secret', h)
    assert not verify_password('wrong', h)

def test_demo_auth_and_workspace_isolation(tmp_path, monkeypatch):
    from app import db
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'test.sqlite3')
    db.init_db(); db.seed_demo()
    from app.auth import authenticate, require_session, require_membership
    s = authenticate('person_david', 'demo-david')
    assert s and s['organization_id'] == 'org_demo'
    assert require_session(s['token'])['user_id'] == 'person_david'
    require_membership(s, 'org_demo')
    try:
        require_membership(s, 'org_other')
        assert False
    except PermissionError:
        pass
