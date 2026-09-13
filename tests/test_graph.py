import os, sqlite3, tempfile
from pathlib import Path
os.environ['PYTHONPATH']=str(Path(__file__).resolve().parents[1]) + ':' + str(Path(__file__).resolve().parents[1]/'canonical_src')


def setup_db(tmp_path, monkeypatch):
    import app.db as db
    monkeypatch.setattr(db, 'DB_PATH', tmp_path/'test.sqlite3')
    db.init_db(); db.seed_demo()
    return db


def test_thread_graph_and_ask(tmp_path, monkeypatch):
    db=setup_db(tmp_path, monkeypatch)
    from app.graph import create_context, create_meeting, create_artifact, create_communication, thread_graph, ask
    cid=create_context('org_demo','ABC Meeting','Prepare client discussion','person_david')
    create_meeting('org_demo','ABC Friday', '2026-09-05T11:00:00+00:00', thread_id='thread_abc', context_id=cid)
    create_artifact('org_demo','quotation.pdf','uploaded','application/pdf',thread_id='thread_abc')
    create_communication('org_demo','person_david',['person_sarah'],'ABC prep','Please prepare the quotation.','2026-09-04T08:00:00+00:00','thread_abc')
    graph=thread_graph('org_demo','thread_abc')
    assert len(graph['meetings']) == 1 and len(graph['artifacts']) == 1 and len(graph['communications']) == 1
    answer=ask('org_demo','ABC quotation')
    assert answer['classification']=='GROUNDED'
    assert any(x['type']=='OperationalThread' for x in answer['sources'])


def test_cross_workspace_member_reference_rejected(tmp_path, monkeypatch):
    db=setup_db(tmp_path, monkeypatch)
    from app.graph import create_context
    with db.connect() as c:
        c.execute("INSERT INTO organizations VALUES (?,?)",('org_other','Other'))
        c.execute("INSERT INTO people VALUES (?,?,?,?)",('person_other','org_other','Other','ASSISTANT'))
    try:
        create_context('org_demo','Bad','Cross workspace','person_other')
        assert False, 'expected rejection'
    except ValueError:
        pass


def test_recommendation_is_non_mutating(tmp_path, monkeypatch):
    setup_db(tmp_path, monkeypatch)
    from app.graph import create_recommendation
    rid=create_recommendation('org_demo','WorkItem','work_missing','Consider clarifying owner','The item has no clear owner','HIGH')
    assert rid.startswith('rec_')
    import app.db as db
    with db.connect() as c:
        row=c.execute('SELECT status FROM recommendations WHERE id=?',(rid,)).fetchone()
        assert row['status']=='OPEN'
