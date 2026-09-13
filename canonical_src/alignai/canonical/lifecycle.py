"""Canonical lifecycle registry and transition execution.

Lifecycle is deliberately distinct from validity, state history, and supersession.
The registry owns lifecycle definitions and legal transitions; canonical history and
lineage objects remain separate concerns.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional, Iterable, Callable
from types import MappingProxyType
from copy import deepcopy
from threading import RLock

from .enums import ActionStatus, LifecycleState
from .errors import InvariantViolation, LifecycleViolation


@dataclass(frozen=True)
class LifecycleTransitionResult:
    object_id: str
    object_type: str
    prior_state: str
    resulting_state: str
    transition_class: str
    effective_at: datetime
    actor_id: Optional[str]
    authority_context_id: Optional[str]
    evidence_ids: tuple[str, ...]
    history_record: Any


class LifecycleTransactionStore:
    """Minimal transactional persistence boundary for lifecycle state + history.

    The store is intentionally storage-agnostic. A production adapter can replace
    this implementation while preserving the same atomic contract: either the
    object mutation and its HistoryRecord become visible together, or neither does.
    """

    def __init__(self):
        self._lock = RLock()
        self._objects: dict[str, Any] = {}
        self._history: dict[str, Any] = {}

    def _persist_object(self, object: Any) -> None:
        self._objects[object.id] = deepcopy(object)

    def _persist_history(self, history_record: Any) -> None:
        self._history[history_record.id] = deepcopy(history_record)

    def commit(self, object: Any, history_record: Any, mutate: Callable[[], None]) -> None:
        with self._lock:
            previous_object = deepcopy(self._objects.get(object.id, object))
            previous_live_object = deepcopy(object)
            previous_history = dict(self._history)
            try:
                mutate()
                self._persist_object(object)
                self._persist_history(history_record)
            except Exception:
                self._objects[object.id] = previous_object
                self._history = previous_history
                object.__dict__.clear()
                object.__dict__.update(deepcopy(previous_live_object).__dict__)
                raise

    def get_object(self, object_id: str) -> Any:
        with self._lock:
            value = self._objects.get(object_id)
            return deepcopy(value) if value is not None else None

    def get_history(self, history_id: str) -> Any:
        with self._lock:
            value = self._history.get(history_id)
            return deepcopy(value) if value is not None else None

    def history_for(self, subject_id: str) -> list[Any]:
        with self._lock:
            return [deepcopy(v) for v in self._history.values() if v.subject_id == subject_id]


@dataclass(frozen=True)
class SupersessionLifecycleContract:
    """Explicit bridge between lifecycle supersession and lineage semantics."""
    requires_supersession: bool = True
    successor_type_must_match: bool = True
    tenant_must_match: bool = True
    successor_must_be_current: bool = True

    def validate(self) -> None:
        if not self.requires_supersession:
            raise InvariantViolation("Lifecycle supersession contract must require a canonical Supersession.")


@dataclass(frozen=True)
class AuthorityTransitionContract:
    """Executable authority requirements for a lifecycle transition.

    Authority is deliberately evaluated from canonical AuthorityGrant /
    Authorization objects rather than treating an opaque ID as proof.
    """
    required: bool = False
    context_type: Optional[str] = None
    actor_relation: str = "ANY"
    require_active: bool = True
    require_action_match: bool = False

    def validate(self) -> None:
        if not self.required:
            if self.context_type is not None:
                raise InvariantViolation("Non-required authority contract cannot declare a context type.")
            return
        if self.context_type not in {"AuthorityGrant", "Authorization"}:
            raise InvariantViolation("Authority contract requires AuthorityGrant or Authorization context type.")
        if self.actor_relation not in {"ANY", "GRANTOR", "RECIPIENT", "AUTHORIZER", "ACTOR"}:
            raise InvariantViolation(f"Unsupported authority actor relation: {self.actor_relation}.")


@dataclass(frozen=True)
class EvidenceTransitionContract:
    """Executable evidence requirements for a lifecycle transition.

    Evidence is not truth and its presence is not itself a truth resolution.
    This contract only answers whether the transition has the minimum canonical
    evidence needed to justify recording the requested lifecycle change.
    """
    required: bool = False
    evidence_type: str = "Evidence"
    subject_relation: str = "NONE"
    minimum_count: int = 1
    require_occurred_at_on_or_before_transition: bool = True

    def validate(self) -> None:
        if self.evidence_type != "Evidence":
            raise InvariantViolation("Lifecycle evidence contract must reference canonical Evidence objects.")
        if self.subject_relation not in {"NONE", "OBJECT"}:
            raise InvariantViolation(f"Unsupported evidence subject relation: {self.subject_relation}.")
        if self.required and self.minimum_count < 1:
            raise InvariantViolation("Required evidence contracts must require at least one evidence object.")
        if not self.required and self.minimum_count != 1:
            raise InvariantViolation("Non-required evidence contracts must use the default minimum count.")


@dataclass(frozen=True)
class LifecycleTransitionSpec:
    source: Enum
    target: Enum
    transition_class: str
    requires_actor: bool = False
    authority: AuthorityTransitionContract = AuthorityTransitionContract()
    evidence: EvidenceTransitionContract = EvidenceTransitionContract()
    supersession: SupersessionLifecycleContract | None = None
    requires_effective_time: bool = True

    def validate(self) -> None:
        self.authority.validate()
        self.evidence.validate()
        if self.supersession is not None:
            self.supersession.validate()


@dataclass(frozen=True)
class LifecycleDefinition:
    object_type: str
    state_enum: type[Enum]
    initial_state: Enum
    terminal_states: frozenset[Enum]
    transitions: Mapping[Enum, frozenset[Enum]]
    transition_specs: Mapping[tuple[Enum, Enum], LifecycleTransitionSpec]

    @property
    def allowed_states(self) -> frozenset[Enum]:
        states = {self.initial_state} | set(self.terminal_states)
        frontier = [self.initial_state]
        while frontier:
            source = frontier.pop()
            for target in self.transitions.get(source, frozenset()):
                if target not in states:
                    states.add(target)
                    frontier.append(target)
        return frozenset(states)

    def validate(self) -> None:
        states = set(self.state_enum)
        if self.initial_state not in states:
            raise InvariantViolation(f"{self.object_type}: initial state is outside its state vocabulary.")
        if not self.terminal_states <= states:
            raise InvariantViolation(f"{self.object_type}: terminal state outside state vocabulary.")
        if set(self.transitions) - states:
            raise InvariantViolation(f"{self.object_type}: transition source outside state vocabulary.")
        for source, targets in self.transitions.items():
            if not targets <= states:
                raise InvariantViolation(f"{self.object_type}: transition target outside state vocabulary.")
            if source in self.terminal_states and targets:
                raise InvariantViolation(f"{self.object_type}: terminal state {source.value} has outgoing transitions.")
            for target in targets:
                if (source, target) not in self.transition_specs:
                    raise InvariantViolation(
                        f"{self.object_type}: transition {source.value}->{target.value} lacks a transition specification."
                    )
        for key, spec in self.transition_specs.items():
            if key != (spec.source, spec.target):
                raise InvariantViolation(f"{self.object_type}: transition specification key mismatch.")
            if spec.source not in states or spec.target not in states:
                raise InvariantViolation(f"{self.object_type}: transition specification uses unknown state.")
            if spec.target not in self.transitions.get(spec.source, frozenset()):
                raise InvariantViolation(f"{self.object_type}: transition specification exists for illegal edge.")
            spec.validate()


WORK_ITEM_TRANSITIONS = {
    LifecycleState.DRAFT: frozenset({LifecycleState.ACTIVE, LifecycleState.CANCELLED}),
    LifecycleState.ACTIVE: frozenset({LifecycleState.ACKNOWLEDGED, LifecycleState.STARTED, LifecycleState.WAITING, LifecycleState.BLOCKED, LifecycleState.ON_HOLD, LifecycleState.COMPLETED, LifecycleState.CANCELLED}),
    LifecycleState.ACKNOWLEDGED: frozenset({LifecycleState.STARTED, LifecycleState.WAITING, LifecycleState.BLOCKED, LifecycleState.ON_HOLD, LifecycleState.COMPLETED, LifecycleState.CANCELLED}),
    LifecycleState.STARTED: frozenset({LifecycleState.WAITING, LifecycleState.BLOCKED, LifecycleState.ON_HOLD, LifecycleState.COMPLETED, LifecycleState.CANCELLED}),
    LifecycleState.WAITING: frozenset({LifecycleState.STARTED, LifecycleState.BLOCKED, LifecycleState.ON_HOLD, LifecycleState.CANCELLED}),
    LifecycleState.BLOCKED: frozenset({LifecycleState.STARTED, LifecycleState.WAITING, LifecycleState.ON_HOLD, LifecycleState.CANCELLED}),
    LifecycleState.ON_HOLD: frozenset({LifecycleState.STARTED, LifecycleState.WAITING, LifecycleState.BLOCKED, LifecycleState.CANCELLED}),
    LifecycleState.COMPLETED: frozenset(),
    LifecycleState.CANCELLED: frozenset(),
    LifecycleState.SUPERSEDED: frozenset(),
}


def _specs(
    transitions: Mapping[Enum, frozenset[Enum]],
    classes: Mapping[tuple[Enum, Enum], str],
    *,
    actor_edges: frozenset[tuple[Enum, Enum]] = frozenset(),
    authority_edges: Mapping[tuple[Enum, Enum], AuthorityTransitionContract] | None = None,
    evidence_edges: Mapping[tuple[Enum, Enum], EvidenceTransitionContract] | None = None,
    supersession_edges: Mapping[tuple[Enum, Enum], SupersessionLifecycleContract] | None = None,
):
    authority_edges = authority_edges or {}
    evidence_edges = evidence_edges or {}
    supersession_edges = supersession_edges or {}
    return {
        (source, target): LifecycleTransitionSpec(
            source,
            target,
            classes.get((source, target), "PROGRESSION"),
            (source, target) in actor_edges,
            authority_edges.get((source, target), AuthorityTransitionContract()),
            evidence_edges.get((source, target), EvidenceTransitionContract()),
            supersession_edges.get((source, target)),
        )
        for source, targets in transitions.items() for target in targets
    }


WORK_ITEM_CLASSES = {
    (LifecycleState.DRAFT, LifecycleState.ACTIVE): "ACTIVATION",
    (LifecycleState.ACTIVE, LifecycleState.ACKNOWLEDGED): "ACKNOWLEDGEMENT",
    (LifecycleState.ACTIVE, LifecycleState.STARTED): "EXECUTION_START",
    (LifecycleState.ACKNOWLEDGED, LifecycleState.STARTED): "EXECUTION_START",
    (LifecycleState.STARTED, LifecycleState.COMPLETED): "COMPLETION",
    (LifecycleState.ACTIVE, LifecycleState.COMPLETED): "COMPLETION",
    (LifecycleState.ACKNOWLEDGED, LifecycleState.COMPLETED): "COMPLETION",
    (LifecycleState.STARTED, LifecycleState.WAITING): "WAITING",
    (LifecycleState.STARTED, LifecycleState.BLOCKED): "BLOCKING",
    (LifecycleState.WAITING, LifecycleState.STARTED): "RESUMPTION",
    (LifecycleState.BLOCKED, LifecycleState.STARTED): "RESUMPTION",
    (LifecycleState.ACTIVE, LifecycleState.ON_HOLD): "ON_HOLD",
    (LifecycleState.ACKNOWLEDGED, LifecycleState.ON_HOLD): "ON_HOLD",
    (LifecycleState.STARTED, LifecycleState.ON_HOLD): "ON_HOLD",
    (LifecycleState.WAITING, LifecycleState.ON_HOLD): "ON_HOLD",
    (LifecycleState.BLOCKED, LifecycleState.ON_HOLD): "ON_HOLD",
    (LifecycleState.ON_HOLD, LifecycleState.STARTED): "RESUMPTION",
}

OPERATIONAL_THREAD_TRANSITIONS = {
    LifecycleState.ACTIVE: frozenset({LifecycleState.COMPLETED, LifecycleState.CANCELLED, LifecycleState.SUPERSEDED}),
    LifecycleState.COMPLETED: frozenset(),
    LifecycleState.CANCELLED: frozenset(),
    LifecycleState.SUPERSEDED: frozenset(),
}

ACTION_TRANSITIONS = {
    ActionStatus.PROPOSED: frozenset({ActionStatus.AUTHORIZED, ActionStatus.REJECTED}),
    ActionStatus.AUTHORIZED: frozenset({ActionStatus.EXECUTING, ActionStatus.REJECTED}),
    ActionStatus.EXECUTING: frozenset({ActionStatus.EXECUTED, ActionStatus.FAILED}),
    ActionStatus.EXECUTED: frozenset(),
    ActionStatus.REJECTED: frozenset(),
    ActionStatus.FAILED: frozenset(),
}

WORK_ITEM_AUTHORITY_CONTRACTS = {
    (LifecycleState.ACTIVE, LifecycleState.ON_HOLD): AuthorityTransitionContract(required=True, context_type="AuthorityGrant", actor_relation="GRANTOR", require_active=True),
    (LifecycleState.ACKNOWLEDGED, LifecycleState.ON_HOLD): AuthorityTransitionContract(required=True, context_type="AuthorityGrant", actor_relation="GRANTOR", require_active=True),
    (LifecycleState.STARTED, LifecycleState.ON_HOLD): AuthorityTransitionContract(required=True, context_type="AuthorityGrant", actor_relation="GRANTOR", require_active=True),
    (LifecycleState.WAITING, LifecycleState.ON_HOLD): AuthorityTransitionContract(required=True, context_type="AuthorityGrant", actor_relation="GRANTOR", require_active=True),
    (LifecycleState.BLOCKED, LifecycleState.ON_HOLD): AuthorityTransitionContract(required=True, context_type="AuthorityGrant", actor_relation="GRANTOR", require_active=True),
}

WORK_ITEM_EVIDENCE_CONTRACTS = {
    (LifecycleState.ACTIVE, LifecycleState.COMPLETED): EvidenceTransitionContract(
        required=True, subject_relation="OBJECT"
    ),
    (LifecycleState.ACKNOWLEDGED, LifecycleState.COMPLETED): EvidenceTransitionContract(
        required=True, subject_relation="OBJECT"
    ),
    (LifecycleState.STARTED, LifecycleState.COMPLETED): EvidenceTransitionContract(
        required=True, subject_relation="OBJECT"
    ),
}

OPERATIONAL_THREAD_EVIDENCE_CONTRACTS = {
    (LifecycleState.ACTIVE, LifecycleState.COMPLETED): EvidenceTransitionContract(
        required=True, subject_relation="OBJECT"
    ),
}

ACTION_EVIDENCE_CONTRACTS = {
    (ActionStatus.EXECUTING, ActionStatus.EXECUTED): EvidenceTransitionContract(
        required=True, subject_relation="OBJECT"
    ),
    (ActionStatus.EXECUTING, ActionStatus.FAILED): EvidenceTransitionContract(
        required=True, subject_relation="OBJECT"
    ),
}


ACTION_AUTHORITY_CONTRACTS = {
    (ActionStatus.PROPOSED, ActionStatus.AUTHORIZED): AuthorityTransitionContract(
        required=True, context_type="Authorization", actor_relation="AUTHORIZER", require_active=True, require_action_match=True
    ),
    (ActionStatus.AUTHORIZED, ActionStatus.EXECUTING): AuthorityTransitionContract(
        required=True, context_type="Authorization", actor_relation="ACTOR", require_active=True, require_action_match=True
    ),
    (ActionStatus.EXECUTING, ActionStatus.EXECUTED): AuthorityTransitionContract(
        required=True, context_type="Authorization", actor_relation="ACTOR", require_active=True, require_action_match=True
    ),
}


def _make_definition(object_type, enum_type, initial, terminal, transitions, classes, *, authority_edges=None, actor_edges=frozenset(), evidence_edges=None, supersession_edges=None):
    definition = LifecycleDefinition(
        object_type=object_type,
        state_enum=enum_type,
        initial_state=initial,
        terminal_states=frozenset(terminal),
        transitions=MappingProxyType({k: frozenset(v) for k, v in transitions.items()}),
        transition_specs=MappingProxyType(_specs(transitions, classes, actor_edges=actor_edges, authority_edges=authority_edges, evidence_edges=evidence_edges, supersession_edges=supersession_edges)),
    )
    definition.validate()
    return definition


OPERATIONAL_THREAD_SUPERSESSION_CONTRACTS = {
    (LifecycleState.ACTIVE, LifecycleState.SUPERSEDED): SupersessionLifecycleContract(),
}

_LIFECYCLE_REGISTRY = {
    "WorkItem": _make_definition("WorkItem", LifecycleState, LifecycleState.DRAFT,
        {LifecycleState.COMPLETED, LifecycleState.CANCELLED}, WORK_ITEM_TRANSITIONS, WORK_ITEM_CLASSES, authority_edges=WORK_ITEM_AUTHORITY_CONTRACTS, evidence_edges=WORK_ITEM_EVIDENCE_CONTRACTS),
    "OperationalThread": _make_definition("OperationalThread", LifecycleState, LifecycleState.ACTIVE,
        {LifecycleState.COMPLETED, LifecycleState.CANCELLED, LifecycleState.SUPERSEDED}, OPERATIONAL_THREAD_TRANSITIONS, {}, evidence_edges=OPERATIONAL_THREAD_EVIDENCE_CONTRACTS, supersession_edges=OPERATIONAL_THREAD_SUPERSESSION_CONTRACTS),
    "Action": _make_definition("Action", ActionStatus, ActionStatus.PROPOSED,
        {ActionStatus.EXECUTED, ActionStatus.REJECTED, ActionStatus.FAILED}, ACTION_TRANSITIONS, {}, authority_edges=ACTION_AUTHORITY_CONTRACTS, evidence_edges=ACTION_EVIDENCE_CONTRACTS),
}
LIFECYCLE_REGISTRY = MappingProxyType(_LIFECYCLE_REGISTRY)


def transition_allowed(object_type: str, current: Enum, target: Enum) -> bool:
    definition = LIFECYCLE_REGISTRY.get(object_type)
    return bool(definition and target in definition.transitions.get(current, frozenset()))


def assert_transition(object_type: str, current: Enum, target: Enum) -> None:
    definition = LIFECYCLE_REGISTRY.get(object_type)
    if definition is None:
        raise LifecycleViolation(f"No lifecycle definition exists for {object_type}.")
    if not isinstance(current, definition.state_enum) or not isinstance(target, definition.state_enum):
        raise LifecycleViolation(f"{object_type}: state values do not belong to the registered lifecycle vocabulary.")
    if not transition_allowed(object_type, current, target):
        raise LifecycleViolation(f"{object_type}: {current.value}->{target.value} is not permitted.")


def _index_authority_objects(authority_objects: Optional[Iterable[Any]]) -> dict[str, Any]:
    if authority_objects is None:
        return {}
    if isinstance(authority_objects, Mapping):
        return dict(authority_objects)
    return {obj.id: obj for obj in authority_objects}


def _evaluate_authority(contract: AuthorityTransitionContract, *, object: Any, actor_id: Optional[str],
                        authority_context_id: Optional[str], at: datetime, authority_objects: Optional[Iterable[Any]]) -> None:
    if not contract.required:
        return
    if not authority_context_id:
        raise LifecycleViolation(f"{type(object).__name__}: transition requires an executable authority context.")
    objects = _index_authority_objects(authority_objects)
    context = objects.get(authority_context_id)
    if context is None:
        raise LifecycleViolation(
            f"{type(object).__name__}: authority context {authority_context_id!r} was not supplied as a canonical authority object."
        )
    if type(context).__name__ != contract.context_type:
        raise LifecycleViolation(
            f"{type(object).__name__}: authority context must be {contract.context_type}, not {type(context).__name__}."
        )
    if contract.require_active and not context.is_active(at):
        raise LifecycleViolation(f"{type(object).__name__}: authority context is not active at transition time.")
    if actor_id is None:
        raise LifecycleViolation(f"{type(object).__name__}: authority-governed transition requires an actor.")
    if contract.context_type == "Authorization":
        if getattr(object, "authorization_id", None) != context.id:
            raise LifecycleViolation("Lifecycle authority context must match the Action authorization reference.")
        if context.actor_id != getattr(object, "actor_id", None):
            raise LifecycleViolation("Action authorization actor does not match the Action actor.")
        grant = objects.get(context.authority_grant_id)
        if grant is None or type(grant).__name__ != "AuthorityGrant":
            raise LifecycleViolation("Authorization lifecycle context requires its canonical AuthorityGrant.")
        if grant.recipient_id != context.actor_id:
            raise LifecycleViolation("Authorization actor must match the authority grant recipient.")
        if grant.grantor_id != context.authorized_by:
            raise LifecycleViolation("Authorization authorizer must match the authority grant grantor.")
        if not grant.is_active(at):
            raise LifecycleViolation("Authorization authority grant is not active at transition time.")
        if contract.require_action_match and context.action_type != getattr(object, "action_type", None):
            raise LifecycleViolation("Authorization action type does not match the lifecycle object action type.")
        expected = {
            "AUTHORIZER": context.authorized_by,
            "ACTOR": context.actor_id,
            "ANY": actor_id,
        }.get(contract.actor_relation)
        if expected is not None and actor_id != expected:
            raise LifecycleViolation("Lifecycle transition actor does not match the authorization authority relation.")
    elif contract.context_type == "AuthorityGrant":
        expected = {
            "GRANTOR": context.grantor_id,
            "RECIPIENT": context.recipient_id,
            "ANY": actor_id,
        }.get(contract.actor_relation)
        if expected is not None and actor_id != expected:
            raise LifecycleViolation("Lifecycle transition actor does not match the authority grant relation.")


def _index_evidence_objects(evidence_objects: Optional[Iterable[Any]]) -> dict[str, Any]:
    if evidence_objects is None:
        return {}
    if isinstance(evidence_objects, Mapping):
        return dict(evidence_objects)
    return {obj.id: obj for obj in evidence_objects}


def _evaluate_evidence(contract: EvidenceTransitionContract, *, object: Any, evidence_ids: Iterable[str],
                       at: datetime, evidence_objects: Optional[Iterable[Any]]) -> None:
    ids = tuple(evidence_ids)
    if not contract.required and not ids:
        return
    if contract.required and len(ids) < contract.minimum_count:
        raise LifecycleViolation(
            f"{type(object).__name__}: transition requires at least {contract.minimum_count} canonical evidence object(s)."
        )
    if len(set(ids)) != len(ids):
        raise LifecycleViolation(f"{type(object).__name__}: lifecycle evidence references must be unique.")
    objects = _index_evidence_objects(evidence_objects)
    for evidence_id in ids:
        evidence = objects.get(evidence_id)
        if evidence is None:
            raise LifecycleViolation(
                f"{type(object).__name__}: evidence {evidence_id!r} was not supplied as a canonical Evidence object."
            )
        if type(evidence).__name__ != contract.evidence_type:
            raise LifecycleViolation(
                f"{type(object).__name__}: lifecycle evidence must be {contract.evidence_type}, not {type(evidence).__name__}."
            )
        if contract.subject_relation == "OBJECT" and getattr(evidence, "subject_id", None) != object.id:
            raise LifecycleViolation(
                f"{type(object).__name__}: evidence {evidence.id!r} must identify the lifecycle object as its subject."
            )
        occurred_at = getattr(evidence, "occurred_at", None)
        if contract.require_occurred_at_on_or_before_transition:
            if occurred_at is None or occurred_at.tzinfo is None:
                raise LifecycleViolation("Lifecycle evidence must have a timezone-aware occurred_at timestamp.")
            if occurred_at > at:
                raise LifecycleViolation(
                    f"{type(object).__name__}: lifecycle evidence cannot occur after the transition effective time."
                )


def _require_aware(at: Optional[datetime]) -> datetime:
    value = at or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise InvariantViolation("Lifecycle transition time must be timezone-aware.")
    return value


def _organization_id(obj: Any) -> Optional[str]:
    envelope = getattr(obj, "envelope", None)
    return getattr(envelope, "organization_id", None) if envelope is not None else None


def _enforce_tenant_boundary(*, object: Any, actor_id: Optional[str], authority_objects: Optional[Iterable[Any]],
                             evidence_objects: Optional[Iterable[Any]], supersession_objects: Optional[Iterable[Any]],
                             organization_id: Optional[str]) -> Optional[str]:
    """Require every scoped participant in a lifecycle transition to agree on one tenant."""
    participants = [object]
    for collection in (authority_objects, evidence_objects, supersession_objects):
        if collection is None:
            continue
        values = collection.values() if isinstance(collection, Mapping) else collection
        participants.extend(list(values))
    scoped = {_organization_id(item) for item in participants if _organization_id(item) is not None}
    object_org = _organization_id(object)
    if organization_id is not None:
        scoped.add(organization_id)
    if len(scoped) > 1:
        raise LifecycleViolation("Lifecycle transition crosses organization boundaries.")
    resolved = next(iter(scoped), organization_id or object_org)
    if object_org is not None and resolved != object_org:
        raise LifecycleViolation("Lifecycle transition tenant does not match the lifecycle object.")
    # Actor tenancy can be checked when a canonical Person is supplied in the authority
    # collection; actor_id alone is intentionally not treated as proof of tenant membership.
    if actor_id and authority_objects:
        people = [item for item in (authority_objects.values() if isinstance(authority_objects, Mapping) else authority_objects)
                  if type(item).__name__ == "Person" and getattr(item, "id", None) == actor_id]
        if people and _organization_id(people[0]) is not None and resolved != _organization_id(people[0]):
            raise LifecycleViolation("Lifecycle transition actor is outside the lifecycle tenant.")
    return resolved


def _evaluate_supersession(contract: SupersessionLifecycleContract, *, object: Any,
                           supersession: Any, successor: Any, at: datetime) -> None:
    from .models import Supersession, ValidityStatus
    if not contract.requires_supersession or not isinstance(supersession, Supersession):
        raise LifecycleViolation("Superseding a lifecycle object requires a canonical Supersession object.")
    if successor is None:
        raise LifecycleViolation("Superseding a lifecycle object requires its successor object.")
    if supersession.previous_id != object.id or supersession.successor_id != successor.id:
        raise LifecycleViolation("Supersession references must match the lifecycle predecessor and successor.")
    if contract.successor_type_must_match and type(object) is not type(successor):
        raise LifecycleViolation("Lifecycle supersession requires successor type to match predecessor type.")
    if contract.successor_must_be_current and successor.envelope.validity_status == ValidityStatus.SUPERSEDED:
        raise LifecycleViolation("Lifecycle supersession successor must not already be superseded.")
    if object.envelope.validity_status == ValidityStatus.SUPERSEDED:
        raise LifecycleViolation("A lifecycle object already marked superseded cannot be superseded again.")
    predecessor_org = _organization_id(object)
    successor_org = _organization_id(successor)
    lineage_org = _organization_id(supersession)
    scoped = {v for v in (predecessor_org, successor_org, lineage_org) if v is not None}
    if contract.tenant_must_match and len(scoped) > 1:
        raise LifecycleViolation("Lifecycle supersession cannot cross organization boundaries.")
    if contract.tenant_must_match and scoped and any(v is None for v in (predecessor_org, successor_org, lineage_org)):
        raise LifecycleViolation("Tenant-scoped lifecycle supersession requires tenant context on all lineage objects.")
    if successor.envelope.created_at < object.envelope.created_at:
        raise LifecycleViolation("Supersession successor cannot predate the lifecycle predecessor.")
    if supersession.superseded_at > at:
        raise LifecycleViolation("Supersession cannot be recorded after the lifecycle transition effective time.")


def _apply_mutation(object: Any, target: Enum, effective_at: datetime) -> None:
    object_type = type(object).__name__
    if object_type == "WorkItem":
        old_state, old_completion, old_envelope = object.lifecycle_state, object.actual_completion, object.envelope
        try:
            object.__dict__["_lifecycle_mutation_allowed"] = True
            object.lifecycle_state = target
            if target == LifecycleState.COMPLETED:
                object.actual_completion = effective_at
            object.envelope = type(old_envelope)(**{**old_envelope.__dict__, "lifecycle_state": target})
        except Exception:
            object.__dict__["_lifecycle_mutation_allowed"] = True
            object.lifecycle_state, object.actual_completion, object.envelope = old_state, old_completion, old_envelope
            raise
        finally:
            object.__dict__["_lifecycle_mutation_allowed"] = False
    elif object_type == "OperationalThread":
        old_envelope = object.envelope
        try:
            object.__dict__["_lifecycle_mutation_allowed"] = True
            object.envelope = type(old_envelope)(**{**old_envelope.__dict__, "lifecycle_state": target})
        except Exception:
            object.envelope = old_envelope
            raise
        finally:
            object.__dict__["_lifecycle_mutation_allowed"] = False
    elif object_type == "Action":
        old_status, old_executed, old_result, old_envelope = object.status, object.executed_at, object.result, object.envelope
        try:
            object.__dict__["_lifecycle_mutation_allowed"] = True
            object.status = target
            if target == ActionStatus.EXECUTED:
                object.executed_at = effective_at
            if target != ActionStatus.EXECUTED:
                object.executed_at = None
            object.envelope = type(old_envelope)(**{**old_envelope.__dict__})
        except Exception:
            object.__dict__["_lifecycle_mutation_allowed"] = True
            object.status, object.executed_at, object.result, object.envelope = old_status, old_executed, old_result, old_envelope
            raise
        finally:
            object.__dict__["_lifecycle_mutation_allowed"] = False



def reconstruct_lifecycle_state(object_type: str, history_records: Iterable[Any], subject_id: str):
    """Reconstruct the authoritative lifecycle state from canonical lifecycle history.

    Reconstruction follows the lineage graph rather than caller ordering. Exactly one
    record must begin at the Registry initial state, every resulting state must have
    at most one successor, every edge must be registered, and timestamps must move
    forward. Competing branches are rejected rather than guessed.
    """
    definition = LIFECYCLE_REGISTRY.get(object_type)
    if definition is None:
        raise LifecycleViolation(f"No lifecycle definition exists for {object_type}.")
    records = [r for r in history_records if getattr(r, "subject_id", None) == subject_id]
    if not records:
        return definition.initial_state
    seen_ids = set()
    for record in records:
        if record.id in seen_ids:
            raise LifecycleViolation("Lifecycle history contains duplicate record IDs.")
        seen_ids.add(record.id)
        if not str(getattr(record, "event_type", "")).startswith("LIFECYCLE:"):
            raise LifecycleViolation("Lifecycle reconstruction requires canonical lifecycle HistoryRecords.")
        if record.occurred_at.tzinfo is None:
            raise LifecycleViolation("Lifecycle history timestamps must be timezone-aware.")
        try:
            definition.state_enum(record.prior_state)
            definition.state_enum(record.resulting_state)
        except ValueError as exc:
            raise LifecycleViolation("Lifecycle history contains an unknown state value.") from exc
        assert_transition(object_type, definition.state_enum(record.prior_state), definition.state_enum(record.resulting_state))
    by_prior = {}
    for record in records:
        if record.prior_state in by_prior:
            raise LifecycleViolation("Lifecycle history contains competing successors from the same state.")
        by_prior[record.prior_state] = record
    initial = definition.initial_state.value
    first = by_prior.get(initial)
    if first is None:
        raise LifecycleViolation("Lifecycle history does not begin at the registered initial state.")
    current = definition.initial_state
    visited = set()
    previous_at = None
    while True:
        record = by_prior.get(current.value)
        if record is None:
            break
        if record.id in visited:
            raise LifecycleViolation("Lifecycle history contains a cycle.")
        visited.add(record.id)
        if previous_at is not None and record.occurred_at < previous_at:
            raise LifecycleViolation("Lifecycle history timestamps move backwards.")
        previous_at = record.occurred_at
        current = definition.state_enum(record.resulting_state)
    if len(visited) != len(records):
        raise LifecycleViolation("Lifecycle history contains a disconnected or competing branch.")
    return current


def hydrate_lifecycle_from_history(object: Any, history_records: Iterable[Any]) -> Enum:
    """Hydrate a lifecycle-bearing object from a verified canonical history chain.

    This is the only supported non-transition path for reconstructing an existing
    persisted lifecycle state. It refuses a target state that cannot be derived from
    the supplied history and updates the object's lifecycle representation only after
    reconstruction succeeds.
    """
    object_type = type(object).__name__
    definition = LIFECYCLE_REGISTRY.get(object_type)
    if definition is None:
        raise LifecycleViolation(f"No lifecycle definition exists for {object_type}.")
    current = reconstruct_lifecycle_state(object_type, history_records, object.id)
    records = [r for r in history_records if getattr(r, "subject_id", None) == object.id]
    if not records:
        if current != definition.initial_state:
            raise LifecycleViolation("Lifecycle hydration without history can only produce the registered initial state.")
        return current
    latest = max(records, key=lambda r: (r.occurred_at, r.id))
    if latest.resulting_state != current.value:
        raise LifecycleViolation("Lifecycle hydration history does not resolve to its latest state.")
    if object_type == "WorkItem":
        object.__dict__["_lifecycle_mutation_allowed"] = True
        try:
            object.lifecycle_state = current
            if current == LifecycleState.COMPLETED:
                object.actual_completion = latest.occurred_at
            object.envelope = type(object.envelope)(**{**object.envelope.__dict__, "lifecycle_state": current, "history_ref": latest.id})
        finally:
            object.__dict__["_lifecycle_mutation_allowed"] = False
    elif object_type == "OperationalThread":
        object.__dict__["_lifecycle_mutation_allowed"] = True
        try:
            object.envelope = type(object.envelope)(**{**object.envelope.__dict__, "lifecycle_state": current, "history_ref": latest.id})
        finally:
            object.__dict__["_lifecycle_mutation_allowed"] = False
    elif object_type == "Action":
        object.__dict__["_lifecycle_mutation_allowed"] = True
        try:
            object.status = current
            if current == ActionStatus.EXECUTED:
                object.executed_at = latest.occurred_at
            object.envelope = type(object.envelope)(**{**object.envelope.__dict__, "history_ref": latest.id})
        finally:
            object.__dict__["_lifecycle_mutation_allowed"] = False
    return current


def transition(object: Any, target: Enum, *, actor_id: Optional[str] = None,
               authority_context_id: Optional[str] = None, evidence_ids: tuple[str, ...] = (),
               at: Optional[datetime] = None, authority_objects: Optional[Iterable[Any]] = None,
               evidence_objects: Optional[Iterable[Any]] = None, organization_id: Optional[str] = None,
               transaction_store: Optional[LifecycleTransactionStore] = None,
               supersession: Any = None, successor: Any = None,
               supersession_objects: Optional[Iterable[Any]] = None) -> LifecycleTransitionResult:
    """Execute a registered transition atomically.

    The Registry validates the complete transition contract before mutating the
    object. A canonical HistoryRecord is created as part of the transition result,
    but persistence remains outside the Registry so lifecycle does not become a
    storage layer. The object is mutated only after the history artifact can be
    constructed successfully.
    """
    object_type = type(object).__name__
    definition = LIFECYCLE_REGISTRY.get(object_type)
    if definition is None:
        raise LifecycleViolation(f"No lifecycle definition exists for {object_type}.")
    current = getattr(object, "lifecycle_state", None)
    if current is None:
        current = getattr(object, "status", None)
    assert_transition(object_type, current, target)
    spec = definition.transition_specs[(current, target)]
    if spec.requires_actor and not actor_id:
        raise LifecycleViolation(f"{object_type}: transition requires an actor.")
    effective_at = _require_aware(at)
    resolved_organization_id = _enforce_tenant_boundary(
        object=object, actor_id=actor_id, authority_objects=authority_objects,
        evidence_objects=evidence_objects, supersession_objects=supersession_objects,
        organization_id=organization_id,
    )
    if spec.supersession is not None:
        _evaluate_supersession(spec.supersession, object=object, supersession=supersession, successor=successor, at=effective_at)
    _evaluate_evidence(
        spec.evidence, object=object, evidence_ids=evidence_ids, at=effective_at,
        evidence_objects=evidence_objects
    )
    _evaluate_authority(
        spec.authority, object=object, actor_id=actor_id, authority_context_id=authority_context_id,
        at=effective_at, authority_objects=authority_objects
    )

    # Preconditions that are intrinsic to the current canonical model.
    if object_type == "WorkItem" and target == LifecycleState.COMPLETED:
        # Completion timestamp is established only after all validation succeeds.
        pass
    if object_type == "Action" and target == ActionStatus.EXECUTED and not getattr(object, "authorization_id", None):
        raise LifecycleViolation("Action: execution requires authorization.")

    # Construct the canonical history artifact before mutation. This makes history
    # creation a transition precondition while keeping persistence outside the registry.
    from .models import HistoryRecord
    history_record = HistoryRecord(
        subject_id=object.id,
        event_type=f"LIFECYCLE:{spec.transition_class}",
        occurred_at=effective_at,
        actor_id=actor_id,
        prior_state=current.value,
        resulting_state=target.value,
        evidence_ids=list(evidence_ids),
        supersession_id=getattr(supersession, "id", None),
    )

    # Apply lifecycle and lineage changes through the same transaction boundary.
    # If persistence fails, the store restores the pre-transition object snapshot
    # and history set, preventing current-state/history divergence.
    def _commit_mutation():
        _apply_mutation(object, target, effective_at)
        if spec.supersession is not None:
            from .models import ObjectEnvelope, ValidityStatus
            object.envelope = ObjectEnvelope(**{**object.envelope.__dict__, "validity_status": ValidityStatus.SUPERSEDED, "history_ref": history_record.id})
        else:
            object.envelope = type(object.envelope)(**{**object.envelope.__dict__, "history_ref": history_record.id})

    if transaction_store is None:
        _commit_mutation()
    else:
        transaction_store.commit(object, history_record, _commit_mutation)
    return LifecycleTransitionResult(
        object_id=object.id,
        object_type=object_type,
        prior_state=current.value,
        resulting_state=target.value,
        transition_class=spec.transition_class,
        effective_at=effective_at,
        actor_id=actor_id,
        authority_context_id=authority_context_id,
        evidence_ids=tuple(evidence_ids),
        history_record=history_record,
    )
