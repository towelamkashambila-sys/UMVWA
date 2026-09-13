from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'canonical_src'))
from alignai.canonical.models import WorkItem, Evidence, AuthorityGrant, Decision
from alignai.canonical.enums import LifecycleState
from alignai.canonical.lifecycle import LifecycleTransactionStore
from .db import connect, utcnow_iso
from .graph import emit_event, record_history, _assert_object


def dt(s): return datetime.fromisoformat(s) if s else None

def row_work(row):
    return dict(row)

def load_work(c, work_id):
    r=c.execute('SELECT * FROM work_items WHERE id=?',(work_id,)).fetchone()
    if not r: raise KeyError('work item not found')
    return r

def canonical_work(r):
    wi=WorkItem(description=r['description'], outcome_id=r['outcome_id'], organization_id=r['organization_id'], id=r['id'], owner_id=r['owner_id'], assignee_id=r['assignee_id'], expected_completion=dt(r['expected_completion']))
    # hydrate lifecycle only through a controlled internal reconstruction for persisted state.
    object.__setattr__(wi, '_lifecycle_mutation_allowed', True)
    wi.lifecycle_state=LifecycleState(r['lifecycle_state'])
    object.__setattr__(wi, '_lifecycle_mutation_allowed', False)
    wi.evidence_ids=json.loads(r['evidence_ids'])
    return wi

def persist_transition(c, wi, result, actual_completion=None):
    c.execute('UPDATE work_items SET lifecycle_state=?, actual_completion=?, evidence_ids=? WHERE id=?',(result.resulting_state, actual_completion, json.dumps(list(result.evidence_ids)), wi.id))
    h=result.history_record
    c.execute('INSERT INTO history VALUES (?,?,?,?,?,?,?,?,?,?,?)',(h.id, wi.envelope.organization_id, h.subject_id,h.event_type,h.occurred_at.isoformat(),h.actor_id,h.prior_state,h.resulting_state,json.dumps(h.evidence_ids),h.envelope.authority_context_id,None))

def transition(work_id, target, actor_id, authority=None, evidence=None, cause=None):
    with connect() as c:
        r=load_work(c,work_id); wi=canonical_work(r); now=datetime.now(timezone.utc)
        auth_objs=[]; auth_id=None
        if authority:
            ag=AuthorityGrant(grantor_id=authority['grantor_id'], recipient_id=authority['recipient_id'], scope=authority['scope'], id=authority['id'], effective_from=dt(authority.get('effective_from')))
            auth_objs=[ag]; auth_id=ag.id
        ev_objs=[]; ev_ids=[]
        if evidence:
            for e in evidence:
                ev=Evidence(description=e['description'], source=e['source'], occurred_at=dt(e['occurred_at']), id=e['id'], subject_id=work_id)
                ev_objs.append(ev); ev_ids.append(ev.id)
        result=wi.transition(LifecycleState(target), actor_id=actor_id, authority_context_id=auth_id, evidence_ids=tuple(ev_ids), at=now, authority_objects=auth_objs, evidence_objects=ev_objs, organization_id=r['organization_id'], transaction_store=LifecycleTransactionStore())
        # Evidence is a first-class persisted canonical object, not merely an ID on the transition.
        for ev in ev_objs:
            c.execute(('INSERT INTO evidence VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET organization_id=EXCLUDED.organization_id, subject_id=EXCLUDED.subject_id, description=EXCLUDED.description, source=EXCLUDED.source, occurred_at=EXCLUDED.occurred_at' if __import__('app.db', fromlist=['_is_postgres'])._is_postgres() else 'INSERT OR REPLACE INTO evidence VALUES (?,?,?,?,?,?)'),(ev.id,r['organization_id'],ev.subject_id,ev.description,ev.source,ev.occurred_at.isoformat()))
        actual = now.isoformat() if result.resulting_state==LifecycleState.COMPLETED.value else r['actual_completion']
        persist_transition(c,wi,result,actual)
        emit_event(c, r['organization_id'], 'WORK_STATE_CHANGED', 'WorkItem', work_id, actor_id, {'prior_state': result.prior_state, 'resulting_state': result.resulting_state, 'transition': result.transition_class}, now.isoformat())
        c.execute('INSERT INTO notifications VALUES (?,?,?,?,?,?,?)',(f'notif_{result.history_record.id}',r['organization_id'],r['assignee_id'] or r['owner_id'],f"{result.transition_class.replace('_',' ').title()}: {r['description']}",work_id,now.isoformat(),None))
        if cause:
            c.execute('UPDATE history SET cause=? WHERE id=?',(cause,result.history_record.id))
        return dict(c.execute('SELECT * FROM work_items WHERE id=?',(work_id,)).fetchone())

def create_work(org, thread, outcome, description, owner, assignee, due=None):
    from uuid import uuid4
    from .temporal import normalize_iso
    wid='work_'+uuid4().hex
    with connect() as c:
        _assert_object(c,org,'OperationalThread',thread)
        _assert_object(c,org,'Outcome',outcome) if False else None
        if not c.execute('SELECT 1 FROM outcomes WHERE organization_id=? AND id=?',(org,outcome)).fetchone(): raise ValueError('outcome is not in this workspace')
        if owner and not c.execute('SELECT 1 FROM people WHERE organization_id=? AND id=?',(org,owner)).fetchone(): raise ValueError('owner is not in this workspace')
        if assignee and not c.execute('SELECT 1 FROM people WHERE organization_id=? AND id=?',(org,assignee)).fetchone(): raise ValueError('assignee is not in this workspace')
        normalized_due=normalize_iso(due) if due else None
        now=utcnow_iso()
        c.execute('INSERT INTO work_items VALUES (?,?,?,?,?,?,?,?,?,?,?)',(wid,org,thread,outcome,description,owner,assignee,'DRAFT',normalized_due,None,'[]'))
        emit_event(c,org,'WORK_CREATED','WorkItem',wid,owner,{'description':description,'thread_id':thread,'assignee_id':assignee},now)
        record_history(c,org,wid,'WORK_CREATED',actor_id=owner,occurred_at=now)
    return wid

def set_capacity(org, assistant, state):
    from uuid import uuid4
    now=utcnow_iso(); cid='cap_'+uuid4().hex
    with connect() as c:
        if not c.execute("SELECT 1 FROM people WHERE organization_id=? AND id=? AND role='ASSISTANT'",(org,assistant)).fetchone(): raise ValueError('capacity owner is not an assistant in this workspace')
        old=c.execute('SELECT state FROM capacity WHERE organization_id=? AND assistant_id=?',(org,assistant)).fetchone()
        cur=c.execute('UPDATE capacity SET state=?, declared_at=? WHERE organization_id=? AND assistant_id=?',(state,now,org,assistant))
        if cur.rowcount==0: c.execute('INSERT INTO capacity VALUES (?,?,?,?,?)',(cid,org,assistant,state,now))
        emit_event(c,org,'CAPACITY_DECLARED','Capacity',cid,assistant,{'assistant_id':assistant,'prior_state':old['state'] if old else None,'state':state},now)
        record_history(c,org,cid,'CAPACITY_DECLARED',actor_id=assistant,occurred_at=now)
    return state

def work_projection(org):
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT * FROM work_items WHERE organization_id=? ORDER BY expected_completion IS NULL, expected_completion',(org,)).fetchall()]

def operational_load(org, assistant):
    active={'ACTIVE','ACKNOWLEDGED','STARTED','WAITING','BLOCKED','ON_HOLD'}
    with connect() as c:
        n=c.execute(f"SELECT COUNT(*) AS count FROM work_items WHERE organization_id=? AND assignee_id=? AND lifecycle_state IN ({','.join('?' for _ in active)})",(org,assistant,*active)).fetchone()['count']
    return n
