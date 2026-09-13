from datetime import datetime, timezone
from .models import *
from .enums import ClaimStatus, ValidationResult, RelationshipType, ConsequenceSupport, InterventionType

def base_fixture():
    org=Organization("AlignAI HQ",id="org_abc")
    exec_=Person("Executive",org.id,id="person_exec")
    asst=Person("Executive Assistant",org.id,id="person_assistant")
    role=Role("Executive Assistant",org.id,id="role_assistant")
    outcome=IntendedOutcome("Obtain and validate supplier quotation",org.id,id="outcome_abc",owner_id=exec_.id)
    cond=SuccessCondition("Quotation received and validated",outcome.id,id="condition_abc")
    outcome.success_condition_ids=[cond.id]
    thread=OperationalThread(outcome.id,org.id,id="thread_abc",participant_ids=[exec_.id,asst.id],success_condition_ids=[cond.id])
    resp=Responsibility(asst.id,"Supplier quotation follow-up",org.id,id="resp_abc")
    work=WorkItem("Request supplier quotation",outcome.id,org.id,id="work_abc",owner_id=exec_.id,assignee_id=asst.id)
    commitment=Commitment("Return quotation status",asst.id,org.id,id="commit_abc")
    obligation=Obligation("Maintain accurate supplier status", "operational duty", asst.id,org.id,id="obligation_abc")
    evidence=Evidence("Supplier quotation email exists","supplier_email",datetime(2026,1,1,10,tzinfo=timezone.utc),id="evidence_abc")
    claim=Claim("Supplier quotation was received",id="claim_abc",status=ClaimStatus.SUPPORTED,supporting_evidence_ids=[evidence.id])
    truth=TruthResolution(claim.id,ClaimStatus.SUPPORTED,"Direct supplier email",datetime(2026,1,1,11,tzinfo=timezone.utc),id="truth_abc",supporting_evidence_ids=[evidence.id])
    thread.responsibility_ids=[resp.id]; thread.work_item_ids=[work.id]; thread.commitment_ids=[commitment.id]; thread.obligation_ids=[obligation.id]; thread.evidence_ids=[evidence.id]; thread.claim_ids=[claim.id]
    permission=Permission(asst.id,"VIEW","supplier_quote",id="permission_abc")
    authority=AuthorityGrant(exec_.id,asst.id,"request_supplier_quote",id="authority_abc")
    authorization=Authorization(asst.id,"REQUEST_QUOTE","supplier_quote",authority.id,exec_.id,id="authz_abc")
    action=Action("REQUEST_QUOTE",asst.id,"supplier_abc",authorization.id,id="action_abc")
    h1=HistoryRecord(action.id,"LIFECYCLE:AUTHORIZATION",datetime(2026,1,2,6,tzinfo=timezone.utc),id="history_action_1",actor_id=exec_.id,prior_state="PROPOSED",resulting_state="AUTHORIZED")
    h2=HistoryRecord(action.id,"LIFECYCLE:EXECUTION_START",datetime(2026,1,2,7,tzinfo=timezone.utc),id="history_action_2",actor_id=asst.id,prior_state="AUTHORIZED",resulting_state="EXECUTING")
    h3=HistoryRecord(action.id,"LIFECYCLE:EXECUTION",datetime(2026,1,2,8,tzinfo=timezone.utc),id="history_action_3",actor_id=asst.id,prior_state="EXECUTING",resulting_state="EXECUTED")
    from .lifecycle import hydrate_lifecycle_from_history
    hydrate_lifecycle_from_history(action,[h1,h2,h3])
    response=ObservedResponse(action.id,"Supplier acknowledged request",datetime(2026,1,2,9,tzinfo=timezone.utc),id="response_abc")
    validation=Validation(cond.id,exec_.id,"email+document",ValidationResult.SATISFIED,datetime(2026,1,2,10,tzinfo=timezone.utc),id="validation_abc",evidence_ids=[evidence.id])
    meeting=Meeting("Supplier review",datetime(2026,1,3,9,tzinfo=timezone.utc),id="meeting_abc",ends_at=datetime(2026,1,3,10,tzinfo=timezone.utc),participant_ids=[exec_.id,asst.id],operational_thread_id=thread.id)
    trace=ProcessingTrace("action_abc",id="trace_abc",stages=["INPUT","IDENTITY","EVIDENCE","TRUTH","TEMPORAL","CHANGE","CONSEQUENCE","SIGNIFICANCE","RESPONSE","PERMISSION","AUTHORITY","AUTHORIZATION","ACTION","OBSERVATION","VALIDATION","FINAL_STATE"],final_state_ref=validation.id)
    return [org,exec_,asst,role,outcome,cond,thread,resp,work,commitment,obligation,evidence,claim,truth,permission,authority,authorization,action,h1,h2,h3,response,validation,meeting,trace]
