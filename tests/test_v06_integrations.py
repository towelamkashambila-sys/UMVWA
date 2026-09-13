from datetime import datetime, timezone, timedelta
from app.db import init_db, connect
from app.graph import create_contact_detail, create_person_relationship, create_voice_note, list_events
from app.temporal import normalize_iso, temporal_state, day_label
from app.service import create_work, transition


import app.db as db
_ORIGINAL_DB_PATH = db.DB_PATH

def setup_function():
    db.DB_PATH = __import__('pathlib').Path('/tmp/umvwa_v06_test.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass
    init_db()
    with connect() as c:
        c.execute("INSERT INTO organizations VALUES ('o','O')")
        c.executemany("INSERT INTO people VALUES (?,?,?,?)", [('d','o','David','EXECUTIVE'),('s','o','Sarah','ASSISTANT')])
        c.execute("INSERT INTO outcomes VALUES ('out','o','Outcome')")
        c.execute("INSERT INTO threads VALUES ('t','o','out','Thread')")
        c.commit()


def test_contacts_and_relationships_are_workspace_scoped():
    cid=create_contact_detail('o','s','email','sarah@example.test','work')
    rid=create_person_relationship('o','d','s','ASSISTANT_TO')
    with connect() as c:
        assert c.execute('SELECT 1 FROM contact_details WHERE id=?',(cid,)).fetchone()
        assert c.execute('SELECT 1 FROM person_relationships WHERE id=?',(rid,)).fetchone()


def test_voice_note_persists_context_and_event():
    vid=create_voice_note('o','s','ABC update',duration_seconds=90,transcript='Quotation is waiting for approval',thread_id='t')
    with connect() as c:
        r=c.execute('SELECT * FROM voice_notes WHERE id=?',(vid,)).fetchone()
        assert r['thread_id']=='t' and r['duration_seconds']==90


def test_temporal_normalization_and_day():
    v=normalize_iso('2026-09-04 10:00:00','Africa/Lusaka')
    assert v.endswith('+00:00')
    assert day_label(v)=='Friday'
    now=datetime(2026,9,4,8,tzinfo=timezone.utc)
    assert temporal_state(v,now,48)=='DUE_SOON'


def test_work_transition_emits_realtime_event_in_same_transaction():
    wid=create_work('o','t','out','Prepare quotation','d','s')
    with connect() as c: c.commit()
    transition(wid,'ACTIVE','d')
    evs=list_events('o')
    assert evs[0]['event_type']=='WORK_STATE_CHANGED'
    assert evs[0]['subject_id']==wid


def test_invalid_voice_note_thread_rejected():
    try: create_voice_note('o','s','bad',thread_id='missing')
    except ValueError as e: assert 'workspace' in str(e)
    else: assert False

def teardown_function():
    db.DB_PATH = _ORIGINAL_DB_PATH
