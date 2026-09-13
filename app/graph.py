from __future__ import annotations
import json
from datetime import datetime, timezone
from uuid import uuid4
from .db import connect, utcnow_iso
from .temporal import normalize_iso, day_label

def _id(prefix): return f"{prefix}_{uuid4().hex}"

def _assert_member(c, org, person):
    if not c.execute("SELECT 1 FROM people WHERE organization_id=? AND id=?", (org, person)).fetchone():
        raise ValueError("person is not a member of this workspace")

def _assert_object(c, org, object_type, object_id):
    tables={
        "OperationalThread":"threads", "WorkItem":"work_items", "Context":"contexts",
        "Meeting":"meetings", "Communication":"communications", "Artifact":"artifacts",
        "VoiceNote":"voice_notes", "Person":"people", "Decision":"decisions",
        "Recommendation":"recommendations", "Dependency":"dependencies", "Evidence":"evidence"
    }
    table=tables.get(object_type)
    if not table: raise ValueError(f"unsupported object type: {object_type}")
    if not c.execute(f"SELECT 1 FROM {table} WHERE organization_id=? AND id=?", (org, object_id)).fetchone():
        raise ValueError(f"{object_type} is not in this workspace")

def emit_event(c, org, event_type, subject_type, subject_id, actor_id=None, payload=None, occurred_at=None):
    eid=_id("event")
    c.execute("INSERT INTO realtime_events VALUES (?,?,?,?,?,?,?,?)", (eid,org,event_type,subject_type,subject_id,actor_id,json.dumps(payload or {},sort_keys=True),occurred_at or utcnow_iso()))
    return eid

def record_history(c, org, subject_id, event_type, actor_id=None, prior_state=None, resulting_state=None, evidence_ids=None, authority_context_id=None, cause=None, occurred_at=None):
    hid=_id("history")
    c.execute("INSERT INTO history VALUES (?,?,?,?,?,?,?,?,?,?,?)", (hid,org,subject_id,event_type,occurred_at or utcnow_iso(),actor_id,prior_state,resulting_state,json.dumps(evidence_ids or []),authority_context_id,cause))
    return hid

def _commit_event(c, org, event_type, subject_type, subject_id, actor_id, payload, occurred_at=None, history_event=None):
    when=occurred_at or utcnow_iso()
    emit_event(c,org,event_type,subject_type,subject_id,actor_id,payload,when)
    if history_event:
        record_history(c,org,subject_id,history_event,actor_id=actor_id,occurred_at=when)

def create_context(org, title, summary, owner_id=None, actor_id=None):
    with connect() as c:
        if owner_id: _assert_member(c,org,owner_id)
        cid=_id("context"); now=utcnow_iso()
        c.execute("INSERT INTO contexts VALUES (?,?,?,?,?)",(cid,org,title,summary,owner_id))
        _commit_event(c,org,"CONTEXT_CREATED","Context",cid,actor_id or owner_id,{"title":title},now,"CONTEXT_CREATED")
        return cid

def create_dependency(org, subject_type, subject_id, depends_on_type, depends_on_id, reason, required_state="COMPLETED", actor_id=None):
    with connect() as c:
        _assert_object(c,org,subject_type,subject_id); _assert_object(c,org,depends_on_type,depends_on_id)
        if subject_type==depends_on_type and subject_id==depends_on_id: raise ValueError("an object cannot depend on itself")
        did=_id("dep"); now=utcnow_iso()
        c.execute("INSERT INTO dependencies VALUES (?,?,?,?,?,?,?,?,?)",(did,org,subject_type,subject_id,depends_on_type,depends_on_id,reason,required_state,now))
        _commit_event(c,org,"DEPENDENCY_CREATED","Dependency",did,actor_id,{"subject_type":subject_type,"subject_id":subject_id,"depends_on_type":depends_on_type,"depends_on_id":depends_on_id},now,"DEPENDENCY_CREATED")
        return did

def create_communication(org, sender_id, recipient_ids, subject, body, occurred_at=None, thread_id=None, actor_id=None):
    with connect() as c:
        _assert_member(c,org,sender_id)
        for p in recipient_ids: _assert_member(c,org,p)
        if thread_id: _assert_object(c,org,"OperationalThread",thread_id)
        cid=_id("comm"); now=normalize_iso(occurred_at) if occurred_at else utcnow_iso()
        c.execute("INSERT INTO communications VALUES (?,?,?,?,?,?,?,?)",(cid,org,sender_id,json.dumps(recipient_ids),subject,body,now,thread_id))
        _commit_event(c,org,"COMMUNICATION_CREATED","Communication",cid,actor_id or sender_id,{"subject":subject,"recipient_ids":recipient_ids,"thread_id":thread_id},now,"COMMUNICATION_CREATED")
        return cid

def create_meeting(org, title, starts_at, ends_at=None, thread_id=None, context_id=None, actor_id=None):
    with connect() as c:
        if thread_id: _assert_object(c,org,"OperationalThread",thread_id)
        if context_id: _assert_object(c,org,"Context",context_id)
        start=normalize_iso(starts_at); end=normalize_iso(ends_at) if ends_at else None
        if end and end < start: raise ValueError("meeting end must not be before start")
        mid=_id("meeting"); now=utcnow_iso()
        c.execute("INSERT INTO meetings VALUES (?,?,?,?,?,?,?)",(mid,org,title,start,end,thread_id,context_id))
        _commit_event(c,org,"MEETING_CREATED","Meeting",mid,actor_id,{"title":title,"starts_at":start,"ends_at":end,"thread_id":thread_id},now,"MEETING_CREATED")
        return mid

def create_artifact(org, name, source, content_type="text/plain", uri=None, thread_id=None, actor_id=None):
    with connect() as c:
        if thread_id: _assert_object(c,org,"OperationalThread",thread_id)
        aid=_id("artifact"); now=utcnow_iso()
        c.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?)",(aid,org,name,source,content_type,uri,thread_id,now))
        _commit_event(c,org,"ARTIFACT_CREATED","Artifact",aid,actor_id,{"name":name,"content_type":content_type,"thread_id":thread_id},now,"ARTIFACT_CREATED")
        return aid

def link_object(org,left_type,left_id,right_type,right_id,relationship,actor_id=None):
    with connect() as c:
        _assert_object(c,org,left_type,left_id); _assert_object(c,org,right_type,right_id)
        if left_type==right_type and left_id==right_id: raise ValueError("an object cannot link to itself")
        exists=c.execute("SELECT 1 FROM object_links WHERE organization_id=? AND left_type=? AND left_id=? AND right_type=? AND right_id=? AND relationship=?",(org,left_type,left_id,right_type,right_id,relationship)).fetchone()
        if exists: raise ValueError("this relationship already exists")
        lid=_id("link"); now=utcnow_iso()
        c.execute("INSERT INTO object_links VALUES (?,?,?,?,?,?,?)",(lid,org,left_type,left_id,right_type,right_id,relationship))
        _commit_event(c,org,"OBJECT_LINKED","ObjectLink",lid,actor_id,{"left_type":left_type,"left_id":left_id,"right_type":right_type,"right_id":right_id,"relationship":relationship},now,"OBJECT_LINKED")
        return lid

def create_recommendation(org,subject_type,subject_id,text,rationale,confidence="MEDIUM", actor_id=None):
    with connect() as c:
        # Recommendations may be exploratory and therefore may reference a not-yet-persisted object.
        # They remain inert until a human acts on them.
        rid=_id("rec"); now=utcnow_iso()
        c.execute("INSERT INTO recommendations VALUES (?,?,?,?,?,?,?,?,?)",(rid,org,subject_type,subject_id,text,rationale,confidence,"OPEN",now))
        _commit_event(c,org,"RECOMMENDATION_CREATED","Recommendation",rid,actor_id,{"subject_type":subject_type,"subject_id":subject_id,"confidence":confidence},now,"RECOMMENDATION_CREATED")
        return rid

def history_for_subject(org, subject_id):
    with connect() as c:
        return [dict(x) for x in c.execute("SELECT * FROM history WHERE organization_id=? AND subject_id=? ORDER BY occurred_at,id",(org,subject_id)).fetchall()]

def thread_graph(org, thread_id):
    with connect() as c:
        thread=c.execute("SELECT * FROM threads WHERE organization_id=? AND id=?",(org,thread_id)).fetchone()
        if not thread: raise KeyError("thread not found")
        work=c.execute("SELECT * FROM work_items WHERE organization_id=? AND thread_id=? ORDER BY expected_completion",(org,thread_id)).fetchall()
        meetings=c.execute("SELECT * FROM meetings WHERE organization_id=? AND thread_id=? ORDER BY starts_at",(org,thread_id)).fetchall()
        comms=c.execute("SELECT * FROM communications WHERE organization_id=? AND thread_id=? ORDER BY occurred_at",(org,thread_id)).fetchall()
        artifacts=c.execute("SELECT * FROM artifacts WHERE organization_id=? AND thread_id=? ORDER BY created_at",(org,thread_id)).fetchall()
        voices=c.execute("SELECT * FROM voice_notes WHERE organization_id=? AND thread_id=? ORDER BY occurred_at",(org,thread_id)).fetchall()
        links=c.execute("SELECT * FROM object_links WHERE organization_id=? AND ((left_type='OperationalThread' AND left_id=?) OR (right_type='OperationalThread' AND right_id=?))",(org,thread_id,thread_id)).fetchall()
        return {'thread':dict(thread),'work':[dict(x) for x in work],'meetings':[dict(x) for x in meetings],'communications':[dict(x) for x in comms],'artifacts':[dict(x) for x in artifacts],'voice_notes':[dict(x) for x in voices],'links':[dict(x) for x in links]}

def _tokens(q): return [t for t in q.lower().strip().replace("?","").split() if len(t)>2]

def ask(org, question, requester_id=None, role=None):
    tokens=_tokens(question)
    with connect() as c:
        # Ask is a permissioned retrieval surface, not a raw database search.
        # The caller must be a real member of this workspace; all retrieval remains
        # tenant-scoped, and sensitive contact values / message bodies / transcripts
        # are never returned as Ask source payloads.
        if requester_id is not None and not c.execute("SELECT 1 FROM people WHERE organization_id=? AND id=?", (org, requester_id)).fetchone():
            raise PermissionError("requester is not a member of this workspace")
        people=c.execute("SELECT * FROM people WHERE organization_id=?",(org,)).fetchall()
        threads=c.execute("SELECT * FROM threads WHERE organization_id=?",(org,)).fetchall()
        candidates=[]
        for p in people:
            text=(p['name']+' '+p['role']).lower(); score=sum(2 for t in tokens if t in text)
            if score: candidates.append((score,'Person',p['id'],p['name']))
        for t in threads:
            text=(t['title']+' '+str(t['outcome_id'])).lower(); score=sum(2 for tok in tokens if tok in text)
            work=c.execute("SELECT * FROM work_items WHERE organization_id=? AND thread_id=?",(org,t['id'])).fetchall()
            comms=c.execute("SELECT * FROM communications WHERE organization_id=? AND thread_id=?",(org,t['id'])).fetchall()
            meetings=c.execute("SELECT * FROM meetings WHERE organization_id=? AND thread_id=?",(org,t['id'])).fetchall()
            voices=c.execute("SELECT * FROM voice_notes WHERE organization_id=? AND thread_id=?",(org,t['id'])).fetchall()
            for w in work: score += sum(1 for tok in tokens if tok in w['description'].lower())
            for m in meetings: score += sum(1 for tok in tokens if tok in m['title'].lower())
            for cm in comms: score += sum(1 for tok in tokens if tok in (cm['subject']+' '+cm['body']).lower())
            for v in voices: score += sum(1 for tok in tokens if tok in ((v['title'] or '')+' '+(v['transcript'] or '')).lower())
            if score: candidates.append((score,'OperationalThread',t['id'],t['title']))
        candidates.sort(key=lambda x:(-x[0],x[1],x[3]))
        if not candidates:
            return {'answer':'I could not ground that question in the current operational reality. Try a person, client, thread, work item, meeting, or voice-note topic.','classification':'UNCERTAIN','sources':[]}
        _,kind,sid,label=candidates[0]
        if kind=='Person':
            p=c.execute("SELECT * FROM people WHERE organization_id=? AND id=?",(org,sid)).fetchone()
            sources=[{'type':'Person','id':sid,'name':p['name'],'role':p['role']}]
            comms=c.execute(("SELECT * FROM communications WHERE organization_id=? AND (sender_id=? OR position(? in recipient_ids)>0) ORDER BY occurred_at DESC LIMIT 10" if __import__('app.db', fromlist=['_is_postgres'])._is_postgres() else "SELECT * FROM communications WHERE organization_id=? AND (sender_id=? OR instr(recipient_ids,?)>0) ORDER BY occurred_at DESC LIMIT 10"),(org,sid,sid)).fetchall()
            # Ask exposes operational metadata, not private contact values or raw message content.
            sources += [{'type':'Communication','id':x['id'],'occurred_at':x['occurred_at'],'subject':x['subject'],'thread_id':x['thread_id']} for x in comms]
            relationships=c.execute("SELECT relationship,related_person_id FROM person_relationships WHERE organization_id=? AND person_id=? UNION ALL SELECT relationship,person_id FROM person_relationships WHERE organization_id=? AND related_person_id=?",(org,sid,org,sid)).fetchall()
            sources += [{'type':'PersonRelationship','relationship':x['relationship'],'related_person_id':x['related_person_id']} for x in relationships]
            return {'answer':f"Person: {label}. I found {len(comms)} recent grounded communication record(s) and {len(relationships)} relationship(s) connected to this person.", 'classification':'GROUNDED','sources':sources}
        graph=thread_graph(org,sid)
        sources=[{'type':'OperationalThread','id':sid,'title':label}]
        from .temporal import temporal_state
        now=datetime.now(timezone.utc)
        sources += [{'type':'WorkItem','id':w['id'],'state':w['lifecycle_state'],'description':w['description'],'temporal_state':(temporal_state(w['expected_completion'],now) if w['expected_completion'] else 'UNSCHEDULED'),'due_day':(day_label(w['expected_completion']) if w['expected_completion'] else None)} for w in graph['work']]
        sources += [{'type':'Meeting','id':m['id'],'starts_at':m['starts_at'],'title':m['title']} for m in graph['meetings']]
        sources += [{'type':'Communication','id':x['id'],'occurred_at':x['occurred_at'],'subject':x['subject']} for x in graph['communications']]
        sources += [{'type':'VoiceNote','id':x['id'],'occurred_at':x['occurred_at'],'title':x['title']} for x in graph['voice_notes']]
        return {'answer':f"Operational thread: {label}. {len(graph['work'])} work item(s), {len(graph['meetings'])} meeting(s), {len(graph['communications'])} communication(s), and {len(graph['voice_notes'])} voice note(s) are grounded in this thread.", 'classification':'GROUNDED','sources':sources}

def create_contact_detail(org,person_id,kind,value,label=None,actor_id=None):
    with connect() as c:
        _assert_member(c,org,person_id); cid=_id("contact"); now=utcnow_iso()
        c.execute("INSERT INTO contact_details VALUES (?,?,?,?,?,?,?)",(cid,org,person_id,kind,value,label,now))
        _commit_event(c,org,"CONTACT_DETAIL_CREATED","ContactDetail",cid,person_id,{"person_id":person_id,"kind":kind},now,"CONTACT_DETAIL_CREATED")
        return cid

def create_person_relationship(org,person_id,related_person_id,relationship,actor_id=None):
    with connect() as c:
        _assert_member(c,org,person_id); _assert_member(c,org,related_person_id)
        if person_id==related_person_id: raise ValueError("a person cannot relate to themselves")
        rid=_id("rel"); now=utcnow_iso()
        c.execute("INSERT INTO person_relationships VALUES (?,?,?,?,?,?)",(rid,org,person_id,related_person_id,relationship,now))
        _commit_event(c,org,"PERSON_RELATIONSHIP_CREATED","PersonRelationship",rid,person_id,{"person_id":person_id,"related_person_id":related_person_id,"relationship":relationship},now,"PERSON_RELATIONSHIP_CREATED")
        return rid

def create_voice_note(org,author_id,title,storage_uri=None,duration_seconds=None,transcript=None,occurred_at=None,thread_id=None,context_id=None):
    with connect() as c:
        _assert_member(c,org,author_id)
        if duration_seconds is not None and duration_seconds<0: raise ValueError("duration cannot be negative")
        if thread_id: _assert_object(c,org,"OperationalThread",thread_id)
        if context_id: _assert_object(c,org,"Context",context_id)
        vid=_id("voice"); occurred=normalize_iso(occurred_at) if occurred_at else utcnow_iso(); now=utcnow_iso()
        c.execute("INSERT INTO voice_notes (id,organization_id,author_id,title,storage_uri,duration_seconds,transcript,transcription_status,occurred_at,thread_id,context_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(vid,org,author_id,title,storage_uri,duration_seconds,transcript,"COMPLETED" if transcript else "PENDING_PROVIDER",occurred,thread_id,context_id,now))
        _commit_event(c,org,"VOICE_NOTE_CREATED","VoiceNote",vid,author_id,{"title":title,"thread_id":thread_id,"context_id":context_id,"has_transcript":bool(transcript)},occurred,"VOICE_NOTE_CREATED")
        return vid

def list_events(org,after=None,limit=100):
    with connect() as c:
        if after: rows=c.execute("SELECT * FROM realtime_events WHERE organization_id=? AND occurred_at>? ORDER BY occurred_at,id LIMIT ?",(org,after,limit)).fetchall()
        else: rows=c.execute("SELECT * FROM realtime_events WHERE organization_id=? ORDER BY occurred_at DESC,id DESC LIMIT ?",(org,limit)).fetchall()
        return [dict(r) for r in rows]

def people_directory(org):
    with connect() as c:
        people=[dict(r) for r in c.execute("SELECT * FROM people WHERE organization_id=? ORDER BY name",(org,)).fetchall()]
        for p in people:
            p['contacts']=[dict(r) for r in c.execute("SELECT * FROM contact_details WHERE organization_id=? AND person_id=? ORDER BY kind",(org,p['id'])).fetchall()]
            p['relationships']=[dict(r) for r in c.execute("SELECT r.*, p.name AS related_person_name FROM person_relationships r JOIN people p ON p.id=r.related_person_id WHERE r.organization_id=? AND r.person_id=? ORDER BY r.relationship",(org,p['id'])).fetchall()]
        return people


def person_profile(org, person_id):
    """Return a permission-neutral operational profile for one workspace person.

    This is deliberately an operational view, not a CRM record: it connects the
    person to the work, meetings, communications, voice notes, decisions,
    dependencies and relationships that already exist in the shared reality.
    """
    with connect() as c:
        person=c.execute("SELECT * FROM people WHERE organization_id=? AND id=?",(org,person_id)).fetchone()
        if not person: raise KeyError("person not found")
        contacts=[dict(r) for r in c.execute("SELECT * FROM contact_details WHERE organization_id=? AND person_id=? ORDER BY kind,id",(org,person_id)).fetchall()]
        relationships=[dict(r) for r in c.execute("""SELECT r.*, p.name AS related_person_name, p.role AS related_person_role
            FROM person_relationships r JOIN people p ON p.id=r.related_person_id
            WHERE r.organization_id=? AND r.person_id=? ORDER BY r.relationship,p.name""",(org,person_id)).fetchall()]
        inverse=[dict(r) for r in c.execute("""SELECT r.*, p.name AS related_person_name, p.role AS related_person_role
            FROM person_relationships r JOIN people p ON p.id=r.person_id
            WHERE r.organization_id=? AND r.related_person_id=? ORDER BY r.relationship,p.name""",(org,person_id)).fetchall()]
        work=[dict(r) for r in c.execute("""SELECT * FROM work_items WHERE organization_id=? AND (owner_id=? OR assignee_id=?)
            ORDER BY expected_completion IS NULL, expected_completion""",(org,person_id,person_id)).fetchall()]
        meetings=[dict(r) for r in c.execute("""SELECT m.* FROM meetings m
            JOIN object_links l ON l.organization_id=m.organization_id AND l.right_type='Meeting' AND l.right_id=m.id
            WHERE m.organization_id=? AND l.left_type='Person' AND l.left_id=?
            ORDER BY m.starts_at""",(org,person_id)).fetchall()]
        # Participation links are the canonical extensibility point; direct sender/recipient
        # membership remains supported for communications until all ingestion is link-based.
        comms=[dict(r) for r in c.execute("SELECT * FROM communications WHERE organization_id=? AND (sender_id=? OR instr(recipient_ids,?)>0) ORDER BY occurred_at DESC",(org,person_id,person_id)).fetchall()]
        voices=[dict(r) for r in c.execute("SELECT * FROM voice_notes WHERE organization_id=? AND author_id=? ORDER BY occurred_at DESC",(org,person_id)).fetchall()]
        decisions=[dict(r) for r in c.execute("SELECT * FROM decisions WHERE organization_id=? AND decision_maker_id=? ORDER BY decided_at DESC",(org,person_id)).fetchall()]
        deps=[dict(r) for r in c.execute("""SELECT * FROM dependencies WHERE organization_id=? AND
            ((subject_type='Person' AND subject_id=?) OR (depends_on_type='Person' AND depends_on_id=?))
            ORDER BY created_at DESC""",(org,person_id,person_id)).fetchall()]
        history=[dict(r) for r in c.execute("SELECT * FROM history WHERE organization_id=? AND actor_id=? ORDER BY occurred_at DESC LIMIT 100",(org,person_id)).fetchall()]
        return {'person':dict(person),'contacts':contacts,'relationships':relationships,'related_to':inverse,
                'work':work,'meetings':meetings,'communications':comms,'voice_notes':voices,
                'decisions':decisions,'dependencies':deps,'history':history}


def operational_story(org, subject_id):
    """Reconstruct the canonical story for one subject plus directly linked activity."""
    with connect() as c:
        _assert_object(c, org, 'WorkItem', subject_id) if c.execute("SELECT 1 FROM work_items WHERE organization_id=? AND id=?", (org, subject_id)).fetchone() else None
        rows = c.execute("SELECT * FROM history WHERE organization_id=? AND subject_id=? ORDER BY occurred_at ASC,id ASC", (org, subject_id)).fetchall()
        events = c.execute("SELECT * FROM realtime_events WHERE organization_id=? AND subject_id=? ORDER BY occurred_at ASC,id ASC", (org, subject_id)).fetchall()
        return {
            'subject_id': subject_id,
            'history': [dict(r) for r in rows],
            'events': [dict(r) for r in events],
            'history_count': len(rows),
            'event_count': len(events),
        }


def due_work(org, now=None, soon_hours=48):
    """Return lifecycle-bearing work with deterministic temporal state."""
    from .temporal import temporal_state
    now = now or datetime.now(timezone.utc)
    with connect() as c:
        rows = c.execute("SELECT * FROM work_items WHERE organization_id=? AND lifecycle_state NOT IN ('COMPLETED','CANCELLED') ORDER BY expected_completion IS NULL, expected_completion", (org,)).fetchall()
        result=[]
        for r in rows:
            item=dict(r)
            item['temporal_state']=temporal_state(r['expected_completion'], now, soon_hours) if r['expected_completion'] else 'UNSCHEDULED'
            item['day']=day_label(r['expected_completion']) if r['expected_completion'] else None
            result.append(item)
        return result
