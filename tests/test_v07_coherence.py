from datetime import datetime, timezone
from app.db import init_db, connect
from app.graph import create_context, create_meeting, create_artifact, create_communication, create_voice_note, create_dependency, link_object, create_recommendation, list_events
from app.service import create_work
import app.db as db
from pathlib import Path

ORIGINAL=db.DB_PATH

def setup_function():
    db.DB_PATH=Path('/tmp/umvwa_v07_coherence.sqlite3')
    try: db.DB_PATH.unlink()
    except FileNotFoundError: pass
    init_db()
    with connect() as c:
        c.execute("INSERT INTO organizations VALUES ('o','O')")
        c.executemany("INSERT INTO people VALUES (?,?,?,?)", [('d','o','David','EXECUTIVE'),('s','o','Sarah','ASSISTANT')])
        c.execute("INSERT INTO outcomes VALUES ('out','o','Outcome')")
        c.execute("INSERT INTO threads VALUES ('t','o','out','ABC')")
        c.commit()

def teardown_function(): db.DB_PATH=ORIGINAL

def test_shared_reality_mutations_emit_events_and_history():
    wid=create_work('o','t','out','Prepare ABC','d','s')
    cid=create_context('o','ABC context','Client preparation','d')
    mid=create_meeting('o','ABC Friday','2026-09-04T11:00:00+02:00',thread_id='t',context_id=cid)
    cmid=create_communication('o','d',['s'],'ABC prep','Please prepare','2026-09-04T08:00:00+02:00','t')
    vid=create_voice_note('o','s','ABC update',transcript='Waiting for approval',occurred_at='2026-09-04T09:00:00+02:00',thread_id='t',context_id=cid)
    aid=create_artifact('o','quotation.pdf','upload','application/pdf',thread_id='t')
    did=create_dependency('o','WorkItem',wid,'Meeting',mid,'Preparation must precede meeting')
    lid=link_object('o','WorkItem',wid,'Artifact',aid,'HAS_EVIDENCE')
    rid=create_recommendation('o','WorkItem',wid,'Clarify approval','Approval dependency exists','HIGH')
    events=list_events('o')
    kinds={e['event_type'] for e in events}
    assert {'WORK_CREATED','CONTEXT_CREATED','MEETING_CREATED','COMMUNICATION_CREATED','VOICE_NOTE_CREATED','ARTIFACT_CREATED','DEPENDENCY_CREATED','OBJECT_LINKED','RECOMMENDATION_CREATED'} <= kinds
    with connect() as c:
        h=c.execute("SELECT event_type FROM history WHERE organization_id='o' AND subject_id=?",(wid,)).fetchall()
    assert any(x['event_type']=='WORK_CREATED' for x in h)

def test_temporal_storage_is_utc_and_meeting_order_is_validated():
    mid=create_meeting('o','ABC','2026-09-04T11:00:00+02:00','2026-09-04T12:00:00+02:00')
    with connect() as c:
        row=c.execute('SELECT starts_at,ends_at FROM meetings WHERE id=?',(mid,)).fetchone()
    assert row['starts_at'].endswith('+00:00') and row['ends_at'].endswith('+00:00')
    try: create_meeting('o','Bad','2026-09-04T12:00:00+00:00','2026-09-04T11:00:00+00:00')
    except ValueError: pass
    else: assert False
