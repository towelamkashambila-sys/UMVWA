from __future__ import annotations
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .db import init_db, seed_demo, connect, database_integrity_check, backup_database, backup_metadata, DB_PATH
from .service import create_work, transition, set_capacity, operational_load
from .graph import create_context, create_dependency, create_communication, create_meeting, create_artifact, link_object, create_recommendation, thread_graph, ask, create_contact_detail, create_person_relationship, create_voice_note, list_events, people_directory, person_profile, operational_story, due_work
from .auth import authenticate, require_session, require_membership, revoke_session, cleanup_expired_sessions
from .temporal import normalize_iso, temporal_state, day_label
from .transcription import transcribe
from .ai import ai_status
from .preferences import get_user_preferences, set_user_preferences, get_org_configuration, set_org_configuration, ALLOWED_USER_KEYS, ALLOWED_ORG_KEYS

@asynccontextmanager
async def lifespan(app):
    init_db()
    if __import__('os').environ.get('UMVWA_SEED_DEMO', '1').lower() in {'1','true','yes'} and __import__('os').environ.get('UMVWA_ENV','development').lower() != 'production':
        seed_demo()
    yield

app=FastAPI(title='UMVWA', version='0.1.0', lifespan=lifespan)

# Lightweight runtime guardrails. These are intentionally dependency-free so the
# same application remains portable from local development to a small pilot host.
_login_attempts: dict[str, list[float]] = {}
_LOGIN_WINDOW_SECONDS = 60
_LOGIN_MAX_ATTEMPTS = 10

@app.middleware('http')
async def runtime_headers(request: Request, call_next):
    request_id = request.headers.get('x-request-id') or __import__('uuid').uuid4().hex
    response = await call_next(request)
    response.headers['X-Request-ID'] = request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api/') else 'no-cache'
    return response
ROOT=Path(__file__).resolve().parents[1]
app.mount('/assets', StaticFiles(directory=ROOT/'assets'), name='assets')
UPLOAD_ROOT=Path(__import__('os').environ.get('UMVWA_VOICE_DIR', str(ROOT/'storage'/'voice'))).expanduser().resolve()
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
MAX_VOICE_BYTES=25*1024*1024
ALLOWED_AUDIO_TYPES={'audio/webm','audio/ogg','audio/wav','audio/x-wav','audio/mpeg','audio/mp4','audio/aac','audio/flac'}


class LoginRequest(BaseModel):
    username: str
    password: str

@app.get('/api/health')
def health():
    with connect() as c:
        c.execute('SELECT 1').fetchone()
    return {'status':'ok','product':'UMVWA','persistence':'reachable'}

@app.get('/api/ready')
def ready():
    try:
        with connect() as c:
            c.execute('SELECT COUNT(*) FROM organizations').fetchone()
        if not database_integrity_check():
            raise HTTPException(503, 'database integrity check failed')
        return {'status':'ready','database':'ready','integrity':'ok'}
    except Exception:
        raise HTTPException(503, 'service not ready')

@app.post('/api/auth/login')
def login(req: LoginRequest, request: Request):
    import time
    now=time.time(); key=(request.client.host if request.client else 'unknown')+'|'+req.username.lower().strip()
    recent=[t for t in _login_attempts.get(key,[]) if now-t < _LOGIN_WINDOW_SECONDS]
    if len(recent) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(429, 'too many login attempts; try again shortly')
    result = authenticate(req.username, req.password)
    if not result:
        recent.append(now); _login_attempts[key]=recent
        raise HTTPException(401, 'invalid credentials')
    _login_attempts.pop(key, None)
    return result

@app.post('/api/auth/logout')
def logout(authorization: str | None = Header(default=None)):
    session = session_from_header(authorization)
    token = authorization[7:].strip()
    revoked = revoke_session(token)
    return {'status':'signed_out','revoked':revoked,'user_id':session['user_id']}

@app.post('/api/auth/cleanup')
def cleanup_sessions(authorization: str | None = Header(default=None)):
    session = session_from_header(authorization)
    if session['role'] != 'EXECUTIVE':
        raise HTTPException(403, 'session cleanup requires executive role')
    return {'removed': cleanup_expired_sessions()}

@app.post('/api/admin/backup')
def create_backup(authorization: str | None = Header(default=None)):
    session = session_from_header(authorization)
    if session['role'] != 'EXECUTIVE':
        raise HTTPException(403, 'database backup requires executive role')
    try:
        path = backup_database()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {'status':'created','database':str(DB_PATH.name), **backup_metadata(path)}


class PreferencesRequest(BaseModel):
    preferences: dict = Field(default_factory=dict)

class WorkspaceConfigRequest(BaseModel):
    configuration: dict = Field(default_factory=dict)

@app.get('/api/preferences')
def preferences(authorization: str | None = Header(default=None)):
    session=session_from_header(authorization)
    return {'preferences':get_user_preferences(session['organization_id'],session['user_id']), 'allowed_keys':sorted(ALLOWED_USER_KEYS)}

@app.patch('/api/preferences')
def update_preferences(req:PreferencesRequest, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization)
    unknown=set(req.preferences)-ALLOWED_USER_KEYS
    if unknown: raise HTTPException(400,f'unsupported preference keys: {sorted(unknown)}')
    return {'preferences':set_user_preferences(session['organization_id'],session['user_id'],req.preferences)}

@app.get('/api/workspace/configuration')
def workspace_configuration(authorization: str | None = Header(default=None)):
    session=session_from_header(authorization)
    return {'configuration':get_org_configuration(session['organization_id']), 'allowed_keys':sorted(ALLOWED_ORG_KEYS)}

@app.patch('/api/workspace/configuration')
def update_workspace_configuration(req:WorkspaceConfigRequest, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization)
    if session['role'] != 'EXECUTIVE': raise HTTPException(403,'workspace configuration requires executive role')
    unknown=set(req.configuration)-ALLOWED_ORG_KEYS
    if unknown: raise HTTPException(400,f'unsupported workspace configuration keys: {sorted(unknown)}')
    return {'configuration':set_org_configuration(session['organization_id'],req.configuration)}

@app.get('/api/ai/status')
def ai_runtime_status(authorization: str | None = Header(default=None)):
    session=session_from_header(authorization)
    return {'organization_id':session['organization_id'], **ai_status()}

@app.get('/api/privacy/export')
def privacy_export(authorization: str | None = Header(default=None)):
    """Export the authenticated person's operationally associated personal data."""
    session=session_from_header(authorization); org=session['organization_id']; person_id=session['user_id']
    with connect() as c:
        person=c.execute('SELECT id,name,role FROM people WHERE id=? AND organization_id=?',(person_id,org)).fetchone()
        contacts=c.execute('SELECT id,kind,label,created_at FROM contact_details WHERE person_id=? AND organization_id=?',(person_id,org)).fetchall()
        relationships=c.execute('SELECT id,related_person_id,relationship,created_at FROM person_relationships WHERE person_id=? AND organization_id=?',(person_id,org)).fetchall()
        work=c.execute('SELECT id,description,lifecycle_state,expected_completion,actual_completion FROM work_items WHERE organization_id=? AND (owner_id=? OR assignee_id=?)',(org,person_id,person_id)).fetchall()
        voice=c.execute('SELECT id,title,duration_seconds,transcription_status,occurred_at,thread_id,context_id FROM voice_notes WHERE organization_id=? AND author_id=?',(org,person_id)).fetchall()
        history=c.execute('SELECT id,subject_id,event_type,occurred_at,prior_state,resulting_state,cause FROM history WHERE organization_id=? AND actor_id=? ORDER BY occurred_at',(org,person_id)).fetchall()
    return {'export_version':'1.0','generated_at':datetime.now(timezone.utc).isoformat(),'person':dict(person) if person else None,'contacts':[dict(x) for x in contacts],'relationships':[dict(x) for x in relationships],'work':[dict(x) for x in work],'voice_notes':[dict(x) for x in voice],'history':[dict(x) for x in history]}

@app.get('/api/privacy/policy')
def privacy_policy():
    return {'retention':'Operational records are retained while the workspace requires them for continuity, audit, and contractual purposes; deletion/retention must be configured with the workspace owner.','ai':'UMVWA does not fabricate transcripts or operational facts. Production AI providers must be explicitly configured.','access':'Workspace access is tenant-scoped and role/authority constrained.','export':'Authenticated users can export their associated operational data through /api/privacy/export.'}

@app.get('/api/auth/session')
def current_session(authorization: str | None = Header(default=None)):
    session = session_from_header(authorization)
    return {k: session[k] for k in ('user_id','organization_id','role','expires_at')}

def session_from_header(authorization: str | None):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'authentication required')
    try:
        return require_session(authorization[7:].strip())
    except PermissionError as e:
        raise HTTPException(401, str(e))

class WorkCreate(BaseModel):
    organization_id:str='org_demo'; thread_id:str='thread_abc'; outcome_id:str='out_demo'; description:str; owner_id:str='person_david'; assignee_id:str='person_sarah'; expected_completion:str|None=None
class TransitionRequest(BaseModel):
    actor_id:str; authority:dict|None=None; evidence:list[dict]=Field(default_factory=list); cause:str|None=None
class CapacityRequest(BaseModel):
    organization_id:str='org_demo'; assistant_id:str='person_sarah'; state:str


class ContextRequest(BaseModel):
    organization_id:str='org_demo'; title:str; summary:str; owner_id:str|None=None
class DependencyRequest(BaseModel):
    organization_id:str='org_demo'; subject_type:str; subject_id:str; depends_on_type:str; depends_on_id:str; reason:str; required_state:str='COMPLETED'
class CommunicationRequest(BaseModel):
    organization_id:str='org_demo'; sender_id:str; recipient_ids:list[str]; subject:str; body:str; occurred_at:str|None=None; thread_id:str|None=None
class MeetingRequest(BaseModel):
    organization_id:str='org_demo'; title:str; starts_at:str; ends_at:str|None=None; thread_id:str|None=None; context_id:str|None=None
class ArtifactRequest(BaseModel):
    organization_id:str='org_demo'; name:str; source:str; content_type:str='text/plain'; uri:str|None=None; thread_id:str|None=None
class LinkRequest(BaseModel):
    organization_id:str='org_demo'; left_type:str; left_id:str; right_type:str; right_id:str; relationship:str
class RecommendationRequest(BaseModel):
    organization_id:str='org_demo'; subject_type:str; subject_id:str; text:str; rationale:str; confidence:str='MEDIUM'
class AskRequest(BaseModel):
    organization_id:str='org_demo'; question:str

class ContactRequest(BaseModel):
    organization_id:str='org_demo'; person_id:str; kind:str; value:str; label:str|None=None
class RelationshipRequest(BaseModel):
    organization_id:str='org_demo'; person_id:str; related_person_id:str; relationship:str
class VoiceNoteRequest(BaseModel):
    organization_id:str='org_demo'; author_id:str; title:str; storage_uri:str|None=None; duration_seconds:int|None=None; transcript:str|None=None; occurred_at:str|None=None; thread_id:str|None=None; context_id:str|None=None
class EventQuery(BaseModel):
    organization_id:str='org_demo'; after:str|None=None; limit:int=100
class TemporalRequest(BaseModel):
    value:str; timezone:str='UTC'

class DecisionRequest(BaseModel):
    organization_id:str='org_demo'; decision:str; decision_maker_id:str='person_david'; authority_grant_id:str; rationale:str|None=None

@app.get('/',response_class=HTMLResponse)
def home():
    return (ROOT/'app'/'index.html').read_text()

@app.get('/api/workspaces/{org_id}')
def workspace(org_id:str, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session, org_id)
    with connect() as c:
        org=c.execute('SELECT * FROM organizations WHERE id=?',(org_id,)).fetchone(); people=c.execute('SELECT id,name,role FROM people WHERE organization_id=?',(org_id,)).fetchall()
        if not org: raise HTTPException(404,'workspace not found')
        return {'organization':dict(org),'people':[dict(p) for p in people]}

@app.post('/api/work')
def work(req:WorkCreate, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session, req.organization_id)
    if req.owner_id and session['user_id'] != req.owner_id and session['role'] != 'EXECUTIVE':
        raise HTTPException(403,'cannot create work on behalf of another owner')
    return {'id':create_work(req.organization_id,req.thread_id,req.outcome_id,req.description,req.owner_id,req.assignee_id,req.expected_completion)}

@app.get('/api/work/{work_id}')
def get_work(work_id:str, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization)
    with connect() as c:
        r=c.execute('SELECT * FROM work_items WHERE id=?',(work_id,)).fetchone()
        if not r: raise HTTPException(404,'work item not found')
        require_membership(session, r['organization_id'])
        h=c.execute('SELECT * FROM history WHERE subject_id=? ORDER BY occurred_at',(work_id,)).fetchall()
        return {'work':dict(r),'history':[dict(x) for x in h]}

@app.post('/api/work/{work_id}/transition/{target}')
def do_transition(work_id:str,target:str,req:TransitionRequest, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization)
    with connect() as c:
        r=c.execute('SELECT organization_id FROM work_items WHERE id=?',(work_id,)).fetchone()
        if not r: raise HTTPException(404,'work item not found')
        require_membership(session, r['organization_id'])
    if session['user_id'] != req.actor_id:
        raise HTTPException(403,'actor must be the authenticated user')
    try: return transition(work_id,target,req.actor_id,req.authority,req.evidence,req.cause)
    except Exception as e: raise HTTPException(400,str(e))

@app.post('/api/capacity')
def capacity(req:CapacityRequest, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session, req.organization_id)
    if session['user_id'] != req.assistant_id: raise HTTPException(403,'capacity is declared by the assistant')
    allowed={'AVAILABLE','BUSY','AT_CAPACITY','OVERLOADED','NOT_AVAILABLE'}
    if req.state not in allowed: raise HTTPException(400,'invalid capacity state')
    return {'state':set_capacity(req.organization_id,req.assistant_id,req.state),'operational_load':operational_load(req.organization_id,req.assistant_id)}

@app.get('/api/executive/{org_id}')
def executive(org_id:str, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session, org_id)
    if session['role'] != 'EXECUTIVE': raise HTTPException(403,'executive surface requires executive role')
    with connect() as c:
        work=[dict(x) for x in c.execute('SELECT * FROM work_items WHERE organization_id=?',(org_id,)).fetchall()]
        cap=c.execute('SELECT * FROM capacity WHERE organization_id=?',(org_id,)).fetchall()
        decisions=[dict(x) for x in c.execute('SELECT * FROM decisions WHERE organization_id=? ORDER BY decided_at DESC',(org_id,)).fetchall()]
    return {'signals':{'at_risk':[x for x in work if x['lifecycle_state'] in ('BLOCKED','WAITING')],'pending_decisions':decisions},'assistant_activity':work,'capacity':[dict(x) for x in cap]}

@app.get('/api/assistant/{org_id}/{assistant_id}')
def assistant(org_id:str,assistant_id:str, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session, org_id)
    if session['user_id'] != assistant_id and session['role'] != 'EXECUTIVE': raise HTTPException(403,'assistant surface access denied')
    with connect() as c: work=[dict(x) for x in c.execute('SELECT * FROM work_items WHERE organization_id=? AND assignee_id=? ORDER BY expected_completion',(org_id,assistant_id)).fetchall()]
    return {'priority_work':work,'operational_load':operational_load(org_id,assistant_id)}

class AuthorityRequest(BaseModel):
    organization_id:str='org_demo'; grantor_id:str='person_david'; recipient_id:str='person_sarah'; scope:str='WORK_ITEM_ON_HOLD'; effective_from:str|None=None; effective_until:str|None=None

@app.post('/api/authorities')
def authority(req:AuthorityRequest, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session, req.organization_id)
    if session['role'] != 'EXECUTIVE' or session['user_id'] != req.grantor_id: raise HTTPException(403,'only the authorized executive may grant authority')
    from uuid import uuid4
    aid='authority_'+uuid4().hex
    with connect() as c:
        c.execute('INSERT INTO authorities VALUES (?,?,?,?,?,?,?,?)',(aid,req.organization_id,req.grantor_id,req.recipient_id,req.scope,req.effective_from,req.effective_until,None))
    return {'id':aid,'scope':req.scope}

@app.post('/api/decisions')
def decision(req:DecisionRequest, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session, req.organization_id)
    if session['user_id'] != req.decision_maker_id or session['role'] != 'EXECUTIVE': raise HTTPException(403,'decision authority denied')
    from uuid import uuid4
    now=datetime.now(timezone.utc).isoformat(); did='decision_'+uuid4().hex
    with connect() as c:
        auth=c.execute('SELECT * FROM authorities WHERE id=? AND organization_id=?',(req.authority_grant_id,req.organization_id)).fetchone()
        if not auth: raise HTTPException(400,'decision requires valid authority context')
        c.execute('INSERT INTO decisions VALUES (?,?,?,?,?,?,?)',(did,req.organization_id,req.decision,req.decision_maker_id,req.authority_grant_id,now,req.rationale))
    return {'id':did,'decided_at':now}


@app.get('/api/contacts/{org_id}')
def contacts(org_id:str, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session,org_id)
    return {'people':people_directory(org_id)}

@app.get('/api/people/{org_id}/{person_id}')
def person(org_id:str, person_id:str, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session,org_id)
    try:
        profile=person_profile(org_id,person_id)
        # Contact values are personal data. An assistant can inspect their own
        # contact details; executive users may inspect workspace people. Other
        # assistant-to-person lookups receive the operational profile without raw
        # contact values.
        if session['role'] != 'EXECUTIVE' and session['user_id'] != person_id:
            profile['contacts']=[]
        return profile
    except KeyError as e:
        raise HTTPException(404,str(e))

@app.post('/api/contacts')
def contact(req:ContactRequest, authorization: str | None = Header(default=None)):
    session=_mutating_session(authorization,req.organization_id)
    if session['role'] != 'EXECUTIVE' and req.person_id != session['user_id']:
        raise HTTPException(403,"cannot edit another person's contact details")
    try: return {'id':create_contact_detail(req.organization_id,req.person_id,req.kind,req.value,req.label,actor_id=session['user_id'])}
    except ValueError as e: raise HTTPException(400,str(e))

@app.post('/api/relationships')
def relationship(req:RelationshipRequest, authorization: str | None = Header(default=None)):
    session=_mutating_session(authorization,req.organization_id)
    if session['role'] != 'EXECUTIVE' and req.person_id != session['user_id']:
        raise HTTPException(403,'cannot create a relationship on behalf of another person')
    try: return {'id':create_person_relationship(req.organization_id,req.person_id,req.related_person_id,req.relationship,actor_id=session['user_id'])}
    except ValueError as e: raise HTTPException(400,str(e))

@app.post('/api/voice-notes/upload')
async def voice_note_upload(request: Request, title: str, occurred_at: str|None=None, thread_id: str|None=None, context_id: str|None=None, organization_id: str='org_demo', authorization: str | None = Header(default=None)):
    session=_mutating_session(authorization, organization_id)
    content_type=(request.headers.get('content-type') or '').split(';',1)[0].lower()
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(415, 'unsupported audio content type')
    data=await request.body()
    if not data: raise HTTPException(400, 'audio body is empty')
    if len(data)>MAX_VOICE_BYTES: raise HTTPException(413, 'voice note exceeds 25 MB limit')
    occurred=normalize_iso(occurred_at) if occurred_at else None
    suffix={
        'audio/webm':'.webm','audio/ogg':'.ogg','audio/wav':'.wav','audio/x-wav':'.wav',
        'audio/mpeg':'.mp3','audio/mp4':'.m4a','audio/aac':'.aac','audio/flac':'.flac'
    }[content_type]
    vid='voice_'+__import__('uuid').uuid4().hex
    path=UPLOAD_ROOT/(vid+suffix)
    path.write_bytes(data)
    try:
        created=create_voice_note(organization_id,session['user_id'],title,str(path.relative_to(ROOT)),len(data),None,occurred,thread_id,context_id)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    result=transcribe(str(path),content_type)
    return {'id':created,'storage_uri':str(path.relative_to(ROOT)),'bytes':len(data),'content_type':content_type,'transcription_status':result.status,'transcript':result.transcript}

@app.get('/api/voice-notes/{voice_id}/audio')
def voice_note_audio(voice_id:str, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization)
    with connect() as c:
        row=c.execute('SELECT * FROM voice_notes WHERE id=?',(voice_id,)).fetchone()
        if not row: raise HTTPException(404,'voice note not found')
        require_membership(session,row['organization_id'])
        uri=row['storage_uri']
    if not uri: raise HTTPException(404,'voice audio not available')
    path=(ROOT/uri).resolve()
    if UPLOAD_ROOT.resolve() not in path.parents or not path.is_file(): raise HTTPException(404,'voice audio not found')
    return FileResponse(path)

@app.post('/api/voice-notes')
def voice_note(req:VoiceNoteRequest, authorization: str | None = Header(default=None)):
    _mutating_session(authorization,req.organization_id)
    try:
        occurred=normalize_iso(req.occurred_at) if req.occurred_at else None
        session=session_from_header(authorization)
        if session['user_id'] != req.author_id:
            raise HTTPException(403,'voice note author must be the authenticated user')
        vid=create_voice_note(req.organization_id,req.author_id,req.title,req.storage_uri,req.duration_seconds,req.transcript,occurred,req.thread_id,req.context_id)
        return {'id':vid}
    except ValueError as e: raise HTTPException(400,str(e))

@app.get('/api/voice-notes/{voice_id}/transcription')
def voice_transcription_status(voice_id:str, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization)
    with connect() as c:
        row=c.execute('SELECT id,organization_id,transcription_status,transcript FROM voice_notes WHERE id=?',(voice_id,)).fetchone()
        if not row: raise HTTPException(404,'voice note not found')
        require_membership(session,row['organization_id'])
        return {'id':row['id'],'status':row['transcription_status'] or ('COMPLETED' if row['transcript'] else 'PENDING_PROVIDER'),'transcript':row['transcript']}

@app.get('/api/voice-notes/{org_id}')
def voice_notes(org_id:str, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session,org_id)
    with connect() as c:
        rows=c.execute('SELECT * FROM voice_notes WHERE organization_id=? ORDER BY occurred_at DESC',(org_id,)).fetchall()
    return {'voice_notes':[dict(r) for r in rows]}

@app.get('/api/notifications/{org_id}')
def notifications(org_id:str, unread_only:bool=False, limit:int=100, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session,org_id)
    if limit < 1 or limit > 500: raise HTTPException(400,'limit must be 1..500')
    with connect() as c:
        if unread_only:
            rows=c.execute('SELECT * FROM notifications WHERE organization_id=? AND recipient_id=? AND read_at IS NULL ORDER BY created_at DESC LIMIT ?', (org_id,session['user_id'],limit)).fetchall()
        else:
            rows=c.execute('SELECT * FROM notifications WHERE organization_id=? AND recipient_id=? ORDER BY created_at DESC LIMIT ?', (org_id,session['user_id'],limit)).fetchall()
    return {'notifications':[dict(r) for r in rows]}

@app.post('/api/notifications/{notification_id}/read')
def mark_notification_read(notification_id:str, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization)
    now=datetime.now(timezone.utc).isoformat()
    with connect() as c:
        row=c.execute('SELECT * FROM notifications WHERE id=?',(notification_id,)).fetchone()
        if not row: raise HTTPException(404,'notification not found')
        require_membership(session,row['organization_id'])
        if row['recipient_id'] != session['user_id']: raise HTTPException(403,'notification recipient required')
        c.execute('UPDATE notifications SET read_at=? WHERE id=?',(now,notification_id))
    return {'id':notification_id,'read_at':now}

@app.get('/api/events/{org_id}/stream')
async def event_stream(org_id:str, after:str|None=None, follow:bool=True, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization)
    try: require_membership(session,org_id)
    except PermissionError as e: raise HTTPException(403,str(e))
    # Authenticated bounded SSE: replay from the supplied cursor, then poll the
    # persisted event ledger for newly committed operational events. This gives
    # the browser a live transport without pretending SQLite is a message broker.
    cursor=after
    initial=list_events(org_id,cursor,100)
    if initial:
        cursor=initial[-1]['occurred_at']

    async def generate():
        nonlocal cursor
        for event in initial:
            yield 'event: operational\n'
            yield 'data: '+json.dumps(event,sort_keys=True)+'\n\n'
        if not follow:
            yield ': close\n\n'
            return
        started=asyncio.get_running_loop().time()
        last_heartbeat=started
        while asyncio.get_running_loop().time()-started < 30:
            await asyncio.sleep(0.5)
            events=list_events(org_id,cursor,100)
            if events:
                for event in events:
                    yield 'event: operational\n'
                    yield 'data: '+json.dumps(event,sort_keys=True)+'\n\n'
                cursor=events[-1]['occurred_at']
                last_heartbeat=asyncio.get_running_loop().time()
            elif asyncio.get_running_loop().time()-last_heartbeat >= 5:
                yield ': keep-alive\n\n'
                last_heartbeat=asyncio.get_running_loop().time()
        yield ': stream-timeout\n\n'

    return StreamingResponse(generate(), media_type='text/event-stream', headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no','Connection':'keep-alive'})

@app.get('/api/events/{org_id}')
def events(org_id:str, after:str|None=None, limit:int=100, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session,org_id)
    if limit < 1 or limit > 500: raise HTTPException(400,'limit must be 1..500')
    return {'events':list_events(org_id,after,limit)}

@app.post('/api/temporal/normalize')
def temporal_normalize(req:TemporalRequest):
    try:
        normalized=normalize_iso(req.value,req.timezone)
        return {'normalized':normalized,'day':day_label(normalized),'state':temporal_state(normalized)}
    except ValueError as e: raise HTTPException(400,str(e))

@app.post('/api/ask')
def ask_umvwa(req:AskRequest, authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session, req.organization_id)
    try:
        return ask(req.organization_id, req.question, requester_id=session['user_id'], role=session['role'])
    except PermissionError as e:
        raise HTTPException(403,str(e))

@app.get('/api/history/{org_id}/{subject_id}')
def history_story(org_id:str,subject_id:str,authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session,org_id)
    try: return operational_story(org_id,subject_id)
    except ValueError as e: raise HTTPException(400,str(e))

@app.get('/api/work/{org_id}/temporal')
def temporal_work(org_id:str,soon_hours:int=48,authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session,org_id)
    if soon_hours < 1 or soon_hours > 720: raise HTTPException(400,'soon_hours must be 1..720')
    return {'work':due_work(org_id,soon_hours=soon_hours)}

@app.get('/api/threads/{org_id}/{thread_id}')
def get_thread(org_id:str,thread_id:str,authorization: str | None = Header(default=None)):
    session=session_from_header(authorization); require_membership(session,org_id)
    try: return thread_graph(org_id,thread_id)
    except KeyError as e: raise HTTPException(404,str(e))

def _mutating_session(authorization, org):
    session=session_from_header(authorization)
    try:
        require_membership(session,org)
    except PermissionError as e:
        raise HTTPException(403,str(e))
    return session

@app.post('/api/contexts')
def context(req:ContextRequest,authorization: str | None = Header(default=None)):
    session=_mutating_session(authorization,req.organization_id)
    owner=req.owner_id or session['user_id']
    if session['role'] != 'EXECUTIVE' and owner != session['user_id']:
        raise HTTPException(403,'cannot create context on behalf of another owner')
    try: return {'id':create_context(req.organization_id,req.title,req.summary,owner,actor_id=session['user_id'])}
    except ValueError as e: raise HTTPException(400,str(e))

@app.post('/api/dependencies')
def dependency(req:DependencyRequest,authorization: str | None = Header(default=None)):
    _mutating_session(authorization,req.organization_id)
    session=_mutating_session(authorization,req.organization_id); return {'id':create_dependency(req.organization_id,req.subject_type,req.subject_id,req.depends_on_type,req.depends_on_id,req.reason,req.required_state,actor_id=session['user_id'])}

@app.post('/api/communications')
def communication(req:CommunicationRequest,authorization: str | None = Header(default=None)):
    session=_mutating_session(authorization,req.organization_id)
    if req.sender_id != session['user_id']:
        raise HTTPException(403,'communication sender must be the authenticated user')
    try: return {'id':create_communication(req.organization_id,req.sender_id,req.recipient_ids,req.subject,req.body,req.occurred_at,req.thread_id,actor_id=session['user_id'])}
    except ValueError as e: raise HTTPException(400,str(e))

@app.post('/api/meetings')
def meeting(req:MeetingRequest,authorization: str | None = Header(default=None)):
    session=_mutating_session(authorization,req.organization_id); return {'id':create_meeting(req.organization_id,req.title,req.starts_at,req.ends_at,req.thread_id,req.context_id,actor_id=session['user_id'])}

@app.post('/api/artifacts')
def artifact(req:ArtifactRequest,authorization: str | None = Header(default=None)):
    session=_mutating_session(authorization,req.organization_id); return {'id':create_artifact(req.organization_id,req.name,req.source,req.content_type,req.uri,req.thread_id,actor_id=session['user_id'])}

@app.post('/api/links')
def link(req:LinkRequest,authorization: str | None = Header(default=None)):
    session=_mutating_session(authorization,req.organization_id); return {'id':link_object(req.organization_id,req.left_type,req.left_id,req.right_type,req.right_id,req.relationship,actor_id=session['user_id'])}

@app.post('/api/recommendations')
def recommendation(req:RecommendationRequest,authorization: str | None = Header(default=None)):
    session=_mutating_session(authorization,req.organization_id); return {'id':create_recommendation(req.organization_id,req.subject_type,req.subject_id,req.text,req.rationale,req.confidence,actor_id=session['user_id'])}
