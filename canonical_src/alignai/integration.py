from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .canonical.models import (
    Action, AuthorityGrant, Decision, Dependency, Evidence, HistoryRecord,
    IntendedOutcome, Meeting, OperationalThread, Organization, Person,
    Recommendation, WorkItem,
)
from .canonical.enums import LifecycleState, RelationshipType, InterventionType
from .canonical.validation import validate_all

UTC = timezone.utc


def now():
    return datetime.now(UTC)


@dataclass
class OperatingModel:
    version: int = 1
    approval_required_for: set[str] = field(default_factory=lambda: {"quotation"})
    escalation_after_hours: int = 24
    executive_terms: Dict[str, str] = field(default_factory=dict)

    def evolve(self, *, approval_required_for=None, escalation_after_hours=None, executive_terms=None):
        return OperatingModel(
            version=self.version + 1,
            approval_required_for=set(self.approval_required_for if approval_required_for is None else approval_required_for),
            escalation_after_hours=self.escalation_after_hours if escalation_after_hours is None else escalation_after_hours,
            executive_terms=dict(self.executive_terms if executive_terms is None else executive_terms),
        )


@dataclass
class OperationalSignal:
    blocked_work_id: str
    prerequisite_work_id: str
    explanation: str
    affected_work_ids: List[str]


@dataclass
class AlignmentRecommendation:
    recommendation: Recommendation
    intervention_type: InterventionType
    requires_human_decision: bool
    confidence: str


@dataclass
class RoleView:
    role: str
    title: str
    summary: str
    next_actions: List[str]
    decisions: List[str]
    blockers: List[str]


@dataclass
class WorkflowState:
    organization: Organization
    executive: Person
    assistant: Person
    outcome: IntendedOutcome
    thread: OperationalThread
    meeting: Meeting
    works: Dict[str, WorkItem]
    dependencies: Dict[str, Dependency]
    history: List[HistoryRecord] = field(default_factory=list)
    operating_model: OperatingModel = field(default_factory=OperatingModel)
    decisions: List[Decision] = field(default_factory=list)


def detect_dependency_signal(state: WorkflowState) -> OperationalSignal:
    blocked = []
    for dep in state.dependencies.values():
        source = state.works.get(dep.source_id)
        target = state.works.get(dep.target_id)
        if not source or not target:
            continue
        # source depends on target: target not complete blocks source.
        if dep.relationship_type == RelationshipType.DEPENDS_ON and target.lifecycle_state != LifecycleState.COMPLETED:
            if source.lifecycle_state not in {LifecycleState.COMPLETED, LifecycleState.CANCELLED}:
                blocked.append(source.id)
                return OperationalSignal(
                    blocked_work_id=source.id,
                    prerequisite_work_id=target.id,
                    explanation=f"{source.description} is blocked because {target.description} is not completed.",
                    affected_work_ids=[source.id],
                )
    raise LookupError("No active dependency blockage detected")


def reason_about_signal(state: WorkflowState, signal: OperationalSignal) -> AlignmentRecommendation:
    prerequisite = state.works[signal.prerequisite_work_id]
    description = prerequisite.description.lower()
    needs_approval = any(term in description for term in state.operating_model.approval_required_for)
    if needs_approval:
        proposal = f"Approve {prerequisite.description} so the blocked work can proceed."
        intervention = InterventionType.REQUEST_DECISION
    else:
        proposal = f"Review {prerequisite.description} and unblock the dependent work."
        intervention = InterventionType.RECOMMEND
    return AlignmentRecommendation(
        recommendation=Recommendation(proposal, signal.explanation),
        intervention_type=intervention,
        requires_human_decision=needs_approval,
        confidence="SUPPORTED",
    )


def executive_view(state: WorkflowState, signal: OperationalSignal, recommendation: AlignmentRecommendation) -> RoleView:
    return RoleView(
        role="Executive",
        title="Decision required",
        summary=signal.explanation,
        next_actions=[recommendation.recommendation.proposal],
        decisions=[recommendation.recommendation.proposal] if recommendation.requires_human_decision else [],
        blockers=[signal.blocked_work_id],
    )


def assistant_view(state: WorkflowState, signal: OperationalSignal, recommendation: AlignmentRecommendation) -> RoleView:
    return RoleView(
        role="Executive Assistant",
        title="Work blocked",
        summary=signal.explanation,
        next_actions=["Prepare the blocked work once the prerequisite is resolved."],
        decisions=[],
        blockers=[signal.blocked_work_id],
    )


def approve_and_execute(state: WorkflowState, signal: OperationalSignal) -> None:
    prerequisite = state.works[signal.prerequisite_work_id]
    t = now()
    grant = AuthorityGrant(state.executive.id, state.assistant.id, "approve-and-execute", effective_from=t)
    decision = Decision("Approve prerequisite", state.executive.id, grant.id, t, rationale=signal.explanation)
    evidence = Evidence(
        description=f"Execution evidence for {prerequisite.description}",
        source="UMVWA workflow execution",
        occurred_at=t,
        subject_id=prerequisite.id,
        reliability="DIRECT",
    )
    state.decisions.append(decision)
    state.history.append(HistoryRecord(prerequisite.id, "DECISION", t, actor_id=state.executive.id))
    for target in (LifecycleState.ACTIVE, LifecycleState.ACKNOWLEDGED, LifecycleState.STARTED):
        result = prerequisite.transition(target, actor_id=state.assistant.id, at=t)
        state.history.append(result.history_record)
    completion = prerequisite.complete(
        at=t,
        actor_id=state.assistant.id,
        evidence_ids=[evidence.id],
        evidence_objects=[evidence],
    )
    state.history.append(completion.history_record)
    blocked = state.works[signal.blocked_work_id]
    for target in (LifecycleState.ACTIVE, LifecycleState.ACKNOWLEDGED, LifecycleState.STARTED):
        result = blocked.transition(target, actor_id=state.assistant.id, at=t)
        state.history.append(result.history_record)


def build_demo_state() -> WorkflowState:
    org = Organization("ABC Limited", id="org_abc")
    executive = Person("Executive", org.id, id="person_exec")
    assistant = Person("Assistant", org.id, id="person_ea")
    outcome = IntendedOutcome("Successful ABC meeting", org.id, id="outcome_meeting")
    thread = OperationalThread(outcome.id, org.id, id="thread_meeting")
    meeting = Meeting("ABC Limited meeting", datetime(2026, 9, 10, 9, tzinfo=UTC), id="meeting_abc", operational_thread_id=thread.id)
    approval = WorkItem("Approve quotation", outcome.id, org.id, id="work_quote", assignee_id=executive.id)
    pack = WorkItem("Finalize meeting pack", outcome.id, org.id, id="work_pack", assignee_id=assistant.id)
    dep = Dependency(pack.id, approval.id, RelationshipType.DEPENDS_ON, id="dep_pack_quote",
                     envelope=approval.envelope.__class__("dep_pack_quote", "Dependency", organization_id=org.id))
    thread.work_item_ids[:] = [approval.id, pack.id]
    thread.dependency_ids[:] = [dep.id]
    validate_all([org, executive, assistant, outcome, thread, meeting, approval, pack, dep])
    return WorkflowState(org, executive, assistant, outcome, thread, meeting,
                         {approval.id: approval, pack.id: pack}, {dep.id: dep})
