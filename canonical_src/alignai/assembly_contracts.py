from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Mapping

class Role(str, Enum):
    EXECUTIVE='EXECUTIVE'; ASSISTANT='ASSISTANT'
class Signal(str, Enum):
    AT_RISK='AT_RISK'; BLOCKED='BLOCKED'; WAITING='WAITING'; NEEDS_INPUT='NEEDS_INPUT'; PENDING_DECISION='PENDING_DECISION'; IMPORTANT_CHANGE='IMPORTANT_CHANGE'; UPCOMING='UPCOMING'; ASSISTANT_ACTIVITY='ASSISTANT_ACTIVITY'
class EvidenceKind(str, Enum):
    FACT='FACT'; SYSTEM_STATE='SYSTEM_STATE'; AI_INFERENCE='AI_INFERENCE'
class UIState(str, Enum):
    LOADING='LOADING'; EMPTY='EMPTY'; READY='READY'; SUCCESS='SUCCESS'; ERROR='ERROR'; UNAUTHORIZED='UNAUTHORIZED'; STALE='STALE'; UNCERTAIN='UNCERTAIN'
class Permission(str, Enum):
    VIEW_SHARED='VIEW_SHARED'; VIEW_PRIVATE='VIEW_PRIVATE'; ASSIGN='ASSIGN'; EDIT='EDIT'; TRANSITION='TRANSITION'; DECIDE='DECIDE'; APPROVE='APPROVE'; AUTHORIZE='AUTHORIZE'; EXECUTE='EXECUTE'; MANAGE_PERMISSIONS='MANAGE_PERMISSIONS'

ASSEMBLY_SUPPORT_TYPES = frozenset({'CapacityDeclaration','OperationalLoad','CapacityImpact','CapacityRecommendation'})

CANONICAL_OBJECTS = frozenset('Organization Person Role IntendedOutcome SuccessCondition OperationalThread Responsibility WorkItem Commitment Obligation Dependency Relationship Event Evidence Claim TruthResolution State Change Consequence SignificanceAssessment Risk Intervention Recommendation Decision Permission AuthorityGrant Delegation Authorization Action ObservedResponse Validation Recovery Notification Meeting Artifact HistoryRecord Correction Supersession ProcessingTrace ExecutionProofRecord'.split())

ROLE_NAV = {
 Role.EXECUTIVE: ('HOME','WORK','ASSISTANT_ACTIVITY','DECISIONS','MEETINGS','COMMUNICATIONS','DOCUMENTS','HISTORY','ASK','NOTIFICATIONS','SETTINGS'),
 Role.ASSISTANT: ('HOME','WORK','PRIORITIES','WAITING','CLARIFICATIONS','APPROVALS','MEETINGS','COMMUNICATIONS','DOCUMENTS','HISTORY','ASK','NOTIFICATIONS','SETTINGS'),
}

ROLE_QUESTIONS = {
 Role.EXECUTIVE: ('What is happening?','What needs me?','What is moving?','What is stuck?','What needs my decision?','What does my assistant need from me?','What changed?'),
 Role.ASSISTANT: ('What do I need to do?','What matters most?','What is due?','What am I waiting on?','What needs clarification?','What needs approval?','What changed?','What should I prepare?','What needs escalation?'),
}

SCREEN_OBJECTS = {
 'HOME': {'OperationalThread','WorkItem','Risk','Decision','Change','Meeting','Notification','Recommendation'},
 'WORK': {'WorkItem','OperationalThread','Dependency','Responsibility','Risk','Recommendation','HistoryRecord'},
 'ASSISTANT_ACTIVITY': {'Person','Role','WorkItem','CapacityDeclaration','Recommendation','Decision'},
 'DECISIONS': {'Decision','Recommendation','Authorization','HistoryRecord','WorkItem'},
 'MEETINGS': {'Meeting','OperationalThread','Person','Artifact','Decision','WorkItem','Dependency'},
 'COMMUNICATIONS': {'Event','Evidence','Claim','OperationalThread','WorkItem','Notification'},
 'DOCUMENTS': {'Artifact','Evidence','Decision','Approval','OperationalThread','WorkItem'},
 'HISTORY': {'HistoryRecord','Event','Change','Decision','Correction','Supersession'},
 'ASK': {'OperationalThread','WorkItem','Dependency','Decision','Risk','Change','HistoryRecord','Recommendation'},
}
# Approval is represented canonically by Decision/Authorization/Action; this alias is a UI concept only.
SCREEN_OBJECTS['DOCUMENTS'].discard('Approval')
SCREEN_OBJECTS['DOCUMENTS'].update({'Decision','Authorization'})

PERMISSION_MATRIX = {
 Role.EXECUTIVE: frozenset({Permission.VIEW_SHARED, Permission.ASSIGN, Permission.EDIT, Permission.TRANSITION, Permission.DECIDE, Permission.APPROVE, Permission.AUTHORIZE}),
 Role.ASSISTANT: frozenset({Permission.VIEW_SHARED, Permission.EDIT, Permission.TRANSITION}),
}

@dataclass(frozen=True)
class StatePropagation:
    source: str
    object_type: str
    event: str
    affected_surfaces: tuple[str,...]
    must_record_history: bool = True

PROPAGATION = (
 StatePropagation('Work','WorkItem','state_change',('HOME','WORK','HISTORY','ASK','NOTIFICATIONS')),
 StatePropagation('Decision Center','Decision','decision_recorded',('HOME','DECISIONS','WORK','HISTORY','ASK','NOTIFICATIONS')),
 StatePropagation('Assistant Activity','WorkItem','capacity_decision',('ASSISTANT_ACTIVITY','HOME','WORK','DECISIONS','HISTORY','NOTIFICATIONS')),
 StatePropagation('Meetings','Meeting','meeting_changed',('HOME','MEETINGS','WORK','HISTORY','ASK')),
 StatePropagation('Communications','Event','communication_ingested',('COMMUNICATIONS','ASK','WORK','HISTORY')),
 StatePropagation('Documents','Artifact','document_changed',('DOCUMENTS','ASK','WORK','HISTORY')),
)

@dataclass(frozen=True)
class Journey:
    id: str
    actor: Role
    steps: tuple[str,...]
    invariants: tuple[str,...]

JOURNEYS = (
 Journey('A_NEW_ASSIGNMENT',Role.EXECUTIVE,('create_work','assign','assistant_acknowledges','start','complete'),('same_canonical_work_item','history_on_transition','role_visibility')),
 Journey('B_CAPACITY_CONFLICT',Role.EXECUTIVE,('assign','capacity_analysis','recommend_tradeoff','human_decision','on_hold_or_reprioritize','notify','history'),('no_silent_mutation','assistant_capacity_authority','decision_recorded')),
 Journey('C_BLOCKED_WORK',Role.ASSISTANT,('mark_blocked','capture_dependency','surface_blocker','notify_relevant_actor','resume_after_resolution'),('blocker_is_explainable','dependency_linked','history_continuous')),
 Journey('D_CLARIFICATION',Role.ASSISTANT,('request_clarification','executive_responds','response_becomes_context','continue_work'),('response_is_operational_history','no_context_loss')),
 Journey('E_APPROVAL',Role.EXECUTIVE,('request_approval','inspect_context','approve_or_reject','record_decision','update_work'),('authority_required','decision_traceable','no_implicit_approval')),
 Journey('F_RETURN_ABSENCE',Role.EXECUTIVE,('open_return_view','review_changes','review_risks','review_decisions','review_assistant_activity','ask_umvwa'),('prioritized_not_exhaustive','facts_distinguished_from_inference')),
 Journey('G_ASK',Role.EXECUTIVE,('ask_question','retrieve_operational_graph','show_evidence','show_inference_if_any','offer_recommendation'),('no_invented_facts','uncertainty_visible','permission_filtered')),
)

FORBIDDEN_PRODUCT_PATTERNS = frozenset({'productivity_score','surveillance_score','private_assistant_monitoring','silent_reprioritization','ai_as_fact','generic_task_dashboard','duplicate_role_dashboards','notification_spam','chatbot_without_operational_grounding'})


def validate_contracts() -> list[str]:
    errors=[]
    if len(CANONICAL_OBJECTS) != 40: errors.append(f'canonical_object_count={len(CANONICAL_OBJECTS)}')
    if set(ROLE_NAV[Role.EXECUTIVE]) == set(ROLE_NAV[Role.ASSISTANT]): errors.append('role navigation must differ')
    if any('productivity' in q.lower() for qs in ROLE_QUESTIONS.values() for q in qs): errors.append('role questions contain productivity framing')
    for surface, objs in SCREEN_OBJECTS.items():
        if not objs <= (CANONICAL_OBJECTS | ASSEMBLY_SUPPORT_TYPES): errors.append(f'{surface}: unknown mapped types {objs-(CANONICAL_OBJECTS|ASSEMBLY_SUPPORT_TYPES)}')
    for role, perms in PERMISSION_MATRIX.items():
        if Permission.VIEW_PRIVATE in perms and role != Role.EXECUTIVE: errors.append('private visibility leaked')
    for p in PROPAGATION:
        if p.object_type not in CANONICAL_OBJECTS: errors.append(f'bad propagation object {p.object_type}')
        if not p.must_record_history: errors.append(f'missing history propagation {p}')
    if len(JOURNEYS) != 7: errors.append('core journey count drift')
    return errors
