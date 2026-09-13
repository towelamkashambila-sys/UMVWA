from pathlib import Path
import app.db as db
from app.db import init_db, connect
from app.graph import create_contact_detail, create_person_relationship, create_voice_note, create_meeting, person_profile

ORIGINAL=db.DB_PATH

def setup_function():
    db.DB_PATH=Path('/tmp/umvwa_v11_people.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass
    init_db()
    with connect() as c:
        c.execute("INSERT INTO organizations VALUES ('o','O')")
        c.executemany("INSERT INTO people VALUES (?,?,?,?)", [('d','o','David','EXECUTIVE'),('s','o','Sarah','ASSISTANT'),('c','o','Client','CLIENT')])
        c.execute("INSERT INTO outcomes VALUES ('out','o','Outcome')")
        c.execute("INSERT INTO threads VALUES ('t','o','out','ABC')")

def teardown_function(): db.DB_PATH=ORIGINAL

def test_person_profile_is_operational_not_just_contact_details():
    create_contact_detail('o','s','email','sarah@example.test','work')
    create_person_relationship('o','d','s','EXECUTIVE_ASSISTANT')
    create_person_relationship('o','c','s','CLIENT_CONTACT')
    vid=create_voice_note('o','s','ABC update',transcript='Waiting for approval',thread_id='t')
    mid=create_meeting('o','ABC Friday','2026-09-04T11:00:00+02:00',thread_id='t')
    with connect() as c:
        c.execute("INSERT INTO object_links VALUES (?,?,?,?,?,?,?)",('link_person_meeting','o','Person','s','Meeting',mid,'ATTENDS'))
    profile=person_profile('o','s')
    assert profile['person']['name']=='Sarah'
    assert profile['contacts'][0]['value']=='sarah@example.test'
    assert any(r['related_person_id']=='s' for r in profile['related_to'])
    assert any(v['id']==vid for v in profile['voice_notes'])
    assert any(m['id']==mid for m in profile['meetings'])

def test_person_profile_cannot_cross_workspace():
    with connect() as c:
        c.execute("INSERT INTO organizations VALUES ('other','Other')")
        c.execute("INSERT INTO people VALUES ('x','other','X','ASSISTANT')")
    try:
        person_profile('o','x')
    except KeyError:
        pass
    else:
        assert False
