from pathlib import Path
import app.db as db
from app.db import init_db, connect
from app.graph import create_communication, create_contact_detail, create_person_relationship, ask

ORIGINAL=db.DB_PATH

def setup_function():
    db.DB_PATH=Path('/tmp/umvwa_v12_permission.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass
    init_db()
    with connect() as c:
        c.execute("INSERT INTO organizations VALUES ('o','O')")
        c.executemany("INSERT INTO people VALUES (?,?,?,?)", [('d','o','David','EXECUTIVE'),('s','o','Sarah','ASSISTANT')])
        c.execute("INSERT INTO outcomes VALUES ('out','o','Outcome')")
        c.execute("INSERT INTO threads VALUES ('t','o','out','ABC')")

def teardown_function(): db.DB_PATH=ORIGINAL

def test_ask_requires_workspace_member():
    try: ask('o','What happened?',requester_id='outsider',role='ASSISTANT')
    except PermissionError: pass
    else: assert False

def test_ask_does_not_expose_raw_message_or_contact_data():
    create_contact_detail('o','s','phone','+260999999','private')
    create_communication('o','s',['d'],'ABC update','Sensitive body',thread_id='t')
    create_person_relationship('o','d','s','EXECUTIVE_ASSISTANT')
    result=ask('o','What happened with Sarah?',requester_id='d',role='EXECUTIVE')
    assert result['classification']=='GROUNDED'
    assert all('body' not in x for x in result['sources'])
    assert all('+260999999' not in str(x) for x in result['sources'])
    assert any(x['type']=='PersonRelationship' for x in result['sources'])
