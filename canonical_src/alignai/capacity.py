from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Sequence

from .canonical.enums import InterventionType, LifecycleState
from .canonical.models import AuthorityGrant, Decision, HistoryRecord, Recommendation, WorkItem
from .canonical.errors import InvariantViolation, LifecycleViolation

UTC = timezone.utc


class CapacityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    AT_CAPACITY = "AT_CAPACITY"
    OVERLOADED = "OVERLOADED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass(frozen=True)
class CapacityDeclaration:
    assistant_id: str
    status: CapacityStatus
    declared_at: datetime
    source: str = "MANUAL"

    def __post_init__(self):
        if not self.assistant_id:
            raise InvariantViolation("Capacity declaration requires an assistant.")
        if self.declared_at.tzinfo is None:
            raise InvariantViolation("Capacity declaration time must be timezone-aware.")
        if self.source not in {"MANUAL", "VOICE"}:
            raise InvariantViolation("Capacity declaration source must be MANUAL or VOICE.")


@dataclass(frozen=True)
class OperationalLoad:
    assistant_id: str
    active_work_ids: tuple[str, ...]
    waiting_work_ids: tuple[str, ...]
    blocked_work_ids: tuple[str, ...]
    due_soon_work_ids: tuple[str, ...]
    meeting_count: int = 0
    commitment_count: int = 0

    @property
    def material_work_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.active_work_ids + self.waiting_work_ids + self.blocked_work_ids))

    @property
    def indicator_count(self) -> int:
        return len(self.material_work_ids) + len(self.due_soon_work_ids) + self.meeting_count + self.commitment_count


@dataclass(frozen=True)
class CapacityImpact:
    declaration: CapacityDeclaration
    load: OperationalLoad
    conflict: bool
    explanation: str


@dataclass(frozen=True)
class CapacityRecommendation:
    recommendation: Recommendation
    intervention_type: InterventionType
    requires_human_decision: bool
    affected_work_ids: tuple[str, ...]


def analyze_operational_load(
    assistant_id: str,
    works: Iterable[WorkItem],
    *,
    now: datetime,
    due_soon_hours: int = 24,
    meeting_count: int = 0,
    commitment_count: int = 0,
) -> OperationalLoad:
    if now.tzinfo is None:
        raise InvariantViolation("Operational load analysis time must be timezone-aware.")
    due_cutoff = now.timestamp() + due_soon_hours * 3600
    active, waiting, blocked, due_soon = [], [], [], []
    for work in works:
        if work.assignee_id != assistant_id:
            continue
        if work.lifecycle_state in {LifecycleState.COMPLETED, LifecycleState.CANCELLED, LifecycleState.DRAFT}:
            continue
        if work.lifecycle_state == LifecycleState.WAITING:
            waiting.append(work.id)
        elif work.lifecycle_state == LifecycleState.BLOCKED:
            blocked.append(work.id)
        elif work.lifecycle_state in {LifecycleState.ACTIVE, LifecycleState.ACKNOWLEDGED, LifecycleState.STARTED, LifecycleState.ON_HOLD}:
            active.append(work.id)
        if work.expected_completion is not None and work.expected_completion.tzinfo is None:
            raise InvariantViolation("WorkItem expected_completion must be timezone-aware when present.")
        if work.expected_completion is not None and work.expected_completion.timestamp() <= due_cutoff:
            due_soon.append(work.id)
    return OperationalLoad(
        assistant_id=assistant_id,
        active_work_ids=tuple(active),
        waiting_work_ids=tuple(waiting),
        blocked_work_ids=tuple(blocked),
        due_soon_work_ids=tuple(dict.fromkeys(due_soon)),
        meeting_count=meeting_count,
        commitment_count=commitment_count,
    )


def analyze_capacity_impact(declaration: CapacityDeclaration, load: OperationalLoad) -> CapacityImpact:
    if declaration.assistant_id != load.assistant_id:
        raise InvariantViolation("Capacity declaration and operational load must identify the same assistant.")
    if declaration.status in {CapacityStatus.AT_CAPACITY, CapacityStatus.OVERLOADED, CapacityStatus.NOT_AVAILABLE}:
        return CapacityImpact(
            declaration, load, True,
            f"Assistant is {declaration.status.value.replace('_', ' ').title()}; a new assignment may affect existing commitments."
        )
    # Declared capacity is authoritative. Operational load can create a potential conflict,
    # but it never rewrites the declaration.
    if load.due_soon_work_ids and load.material_work_ids:
        return CapacityImpact(
            declaration, load, True,
            "Operational load indicates a potential conflict because existing work includes near-term commitments."
        )
    return CapacityImpact(declaration, load, False, "No material capacity conflict detected from the current operational evidence.")


def recommend_tradeoff(
    impact: CapacityImpact,
    *,
    candidate_work: Sequence[WorkItem] = (),
) -> CapacityRecommendation:
    if not impact.conflict:
        rec = Recommendation("No workload adjustment recommended.", impact.explanation)
        return CapacityRecommendation(rec, InterventionType.NO_INTERVENTION, False, ())

    candidates = [w for w in candidate_work if w.id in impact.load.material_work_ids]
    # Recommendation only: never mutate work and never choose silently between equal candidates.
    lower_priority = [w for w in candidates if w.expected_completion is not None]
    if lower_priority:
        lower_priority.sort(key=lambda w: (w.expected_completion, w.id), reverse=True)
        affected = (lower_priority[0].id,)
        proposal = f"Consider placing {lower_priority[0].description} On Hold to protect existing commitments."
    else:
        affected = ()
        proposal = "Review current commitments and negotiate workload before proceeding with the new assignment."
    rec = Recommendation(proposal, impact.explanation)
    return CapacityRecommendation(rec, InterventionType.ADJUST, True, affected)


def apply_human_capacity_decision(
    *,
    work: WorkItem,
    executive_id: str,
    authority_grant: AuthorityGrant,
    decision_time: datetime,
    rationale: str,
) -> tuple[Decision, HistoryRecord]:
    if authority_grant.grantor_id != executive_id:
        raise LifecycleViolation("Capacity decision must be made by the authority grantor.")
    if not authority_grant.is_active(decision_time):
        raise LifecycleViolation("Capacity decision authority must be active at decision time.")
    decision = Decision(
        "Place work on hold to resolve workload conflict",
        executive_id,
        authority_grant.id,
        decision_time,
        rationale=rationale,
        affected_outcome_ids=[work.outcome_id],
    )
    result = work.transition(
        LifecycleState.ON_HOLD,
        actor_id=executive_id,
        authority_context_id=authority_grant.id,
        authority_objects=[authority_grant],
        at=decision_time,
    )
    return decision, result.history_record
