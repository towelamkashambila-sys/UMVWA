from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4
from .enums import *
from .errors import InvariantViolation, LifecycleViolation

SCHEMA_VERSION="1.0"

def utcnow(): return datetime.now(timezone.utc)
def new_id(prefix): return f"{prefix}_{uuid4().hex}"

@dataclass(frozen=True)
class ObjectEnvelope:
    id:str
    object_type:str
    schema_version:str=SCHEMA_VERSION
    object_version:int=1
    status:ObjectStatus=ObjectStatus.ACTIVE
    created_at:datetime=field(default_factory=utcnow)
    effective_at:Optional[datetime]=None
    recorded_at:datetime=field(default_factory=utcnow)
    expires_at:Optional[datetime]=None
    validity_status:ValidityStatus=ValidityStatus.VALID
    actor_id:Optional[str]=None
    authority_context_id:Optional[str]=None
    history_ref:Optional[str]=None
    trace_ref:Optional[str]=None
    organization_id:Optional[str]=None
    lifecycle_state:Optional[LifecycleState]=None
    def __post_init__(self):
        if not self.id: raise InvariantViolation("Canonical objects require stable IDs.")
        if not self.object_type: raise InvariantViolation("Canonical objects require an object type.")
        if not self.schema_version: raise InvariantViolation("Schema version is required.")
        if self.object_version<1: raise InvariantViolation("Object version must be >= 1.")
        for name, value in (("created_at", self.created_at), ("recorded_at", self.recorded_at),
                            ("effective_at", self.effective_at), ("expires_at", self.expires_at)):
            if value is not None and value.tzinfo is None:
                raise InvariantViolation(f"{name} must be timezone-aware.")
        if self.expires_at and self.effective_at and self.expires_at < self.effective_at: raise InvariantViolation("expires_at cannot precede effective_at.")
        if self.recorded_at < self.created_at: raise InvariantViolation("recorded_at cannot precede created_at.")

def env(obj, typ, **kw): return ObjectEnvelope(obj, typ, **kw)

@dataclass
class Organization:
    name:str; id:str=field(default_factory=lambda:new_id("org")); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Organization",organization_id=self.id)

@dataclass
class Person:
    name:str; organization_id:str; id:str=field(default_factory=lambda:new_id("person")); role_ids:list[str]=field(default_factory=list); permission_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Person",organization_id=self.organization_id,actor_id=self.id)

@dataclass
class Role:
    name:str; organization_id:str; id:str=field(default_factory=lambda:new_id("role")); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Role",organization_id=self.organization_id)

@dataclass
class IntendedOutcome:
    description:str; organization_id:str; id:str=field(default_factory=lambda:new_id("outcome")); success_condition_ids:list[str]=field(default_factory=list); owner_id:Optional[str]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"IntendedOutcome",organization_id=self.organization_id)

@dataclass
class SuccessCondition:
    description:str; outcome_id:str; id:str=field(default_factory=lambda:new_id("condition")); validation_ids:list[str]=field(default_factory=list); satisfied:bool=False; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"SuccessCondition")

@dataclass
class OperationalThread:
    intended_outcome_id:str; organization_id:str; id:str=field(default_factory=lambda:new_id("thread")); success_condition_ids:list[str]=field(default_factory=list); participant_ids:list[str]=field(default_factory=list); responsibility_ids:list[str]=field(default_factory=list); work_item_ids:list[str]=field(default_factory=list); commitment_ids:list[str]=field(default_factory=list); obligation_ids:list[str]=field(default_factory=list); dependency_ids:list[str]=field(default_factory=list); evidence_ids:list[str]=field(default_factory=list); claim_ids:list[str]=field(default_factory=list); decision_ids:list[str]=field(default_factory=list); intervention_ids:list[str]=field(default_factory=list); validation_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __setattr__(self, name, value):
        if name == "envelope" and getattr(self, "_lifecycle_initialized", False) and not getattr(self, "_lifecycle_mutation_allowed", False) and value is not None:
            if value.lifecycle_state != self.lifecycle_state:
                raise LifecycleViolation("OperationalThread envelope lifecycle state is registry-managed; use transition().")
        object.__setattr__(self, name, value)
    def __post_init__(self):
        from .lifecycle import LIFECYCLE_REGISTRY
        definition = LIFECYCLE_REGISTRY["OperationalThread"]
        if self.envelope is not None and self.envelope.lifecycle_state != definition.initial_state:
            raise InvariantViolation("OperationalThread construction must begin at the registered initial lifecycle state.")
        self.envelope=self.envelope or env(self.id,"OperationalThread",organization_id=self.organization_id,lifecycle_state=definition.initial_state)
        if self.envelope.lifecycle_state != definition.initial_state:
            raise InvariantViolation("OperationalThread construction must begin at the registered initial lifecycle state.")
        object.__setattr__(self, "_lifecycle_initialized", True)
        object.__setattr__(self, "_lifecycle_mutation_allowed", False)
    @property
    def lifecycle_state(self): return self.envelope.lifecycle_state
    @lifecycle_state.setter
    def lifecycle_state(self, value):
        if getattr(self, "_lifecycle_initialized", False) and not getattr(self, "_lifecycle_mutation_allowed", False):
            raise LifecycleViolation("OperationalThread lifecycle state is registry-managed; use transition().")
        self.envelope=ObjectEnvelope(**{**self.envelope.__dict__, "lifecycle_state": value})
    def transition(self,to_state:LifecycleState, *, actor_id=None, authority_context_id=None, evidence_ids=(), at=None, authority_objects=None, evidence_objects=None, organization_id=None, transaction_store=None, supersession=None, successor=None, supersession_objects=None):
        from .lifecycle import transition
        return transition(self, to_state, actor_id=actor_id, authority_context_id=authority_context_id, evidence_ids=tuple(evidence_ids), at=at, authority_objects=authority_objects, evidence_objects=evidence_objects, organization_id=organization_id, transaction_store=transaction_store, supersession=supersession, successor=successor, supersession_objects=supersession_objects)

@dataclass
class Responsibility:
    person_id:str; concern:str; organization_id:str; id:str=field(default_factory=lambda:new_id("resp")); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Responsibility",organization_id=self.organization_id,actor_id=self.person_id)

@dataclass
class WorkItem:
    description:str; outcome_id:str; organization_id:str; id:str=field(default_factory=lambda:new_id("work")); owner_id:Optional[str]=None; assignee_id:Optional[str]=None; lifecycle_state:LifecycleState=LifecycleState.DRAFT; expected_completion:Optional[datetime]=None; actual_completion:Optional[datetime]=None; evidence_ids:list[str]=field(default_factory=list); dependency_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __setattr__(self, name, value):
        if getattr(self, "_lifecycle_initialized", False) and not getattr(self, "_lifecycle_mutation_allowed", False):
            if name == "lifecycle_state":
                raise LifecycleViolation("WorkItem lifecycle state is registry-managed; use transition().")
            if name == "envelope" and value is not None:
                if value.lifecycle_state != self.lifecycle_state:
                    raise LifecycleViolation("WorkItem envelope lifecycle state is registry-managed; use transition().")
        object.__setattr__(self, name, value)
    def __post_init__(self):
        from .lifecycle import LIFECYCLE_REGISTRY
        definition = LIFECYCLE_REGISTRY["WorkItem"]
        if self.lifecycle_state != definition.initial_state:
            raise InvariantViolation("WorkItem construction must begin at the registered initial lifecycle state; use transition().")
        self.envelope=self.envelope or env(self.id,"WorkItem",organization_id=self.organization_id,lifecycle_state=self.lifecycle_state)
        if self.envelope.lifecycle_state != definition.initial_state:
            raise InvariantViolation("WorkItem envelope lifecycle state must begin at the registered initial lifecycle state.")
        object.__setattr__(self, "_lifecycle_initialized", True)
        object.__setattr__(self, "_lifecycle_mutation_allowed", False)
    def transition(self,to_state:LifecycleState, *, actor_id=None, authority_context_id=None, evidence_ids=(), at=None, authority_objects=None, evidence_objects=None, organization_id=None, transaction_store=None, supersession=None, successor=None, supersession_objects=None):
        from .lifecycle import transition
        return transition(self, to_state, actor_id=actor_id, authority_context_id=authority_context_id, evidence_ids=tuple(evidence_ids), at=at, authority_objects=authority_objects, evidence_objects=evidence_objects, organization_id=organization_id, transaction_store=transaction_store, supersession=supersession, successor=successor, supersession_objects=supersession_objects)
    def complete(self,at=None, *, actor_id=None, authority_context_id=None, evidence_ids=(), authority_objects=None, evidence_objects=None, organization_id=None, transaction_store=None):
        return self.transition(LifecycleState.COMPLETED, actor_id=actor_id, authority_context_id=authority_context_id, evidence_ids=evidence_ids, at=at, authority_objects=authority_objects, evidence_objects=evidence_objects, organization_id=organization_id, transaction_store=transaction_store)

@dataclass
class Commitment:
    description:str; actor_id:str; organization_id:str; id:str=field(default_factory=lambda:new_id("commit")); due_at:Optional[datetime]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Commitment",organization_id=self.organization_id,actor_id=self.actor_id)

@dataclass
class Obligation:
    description:str; basis:str; responsible_actor_id:str; organization_id:str; id:str=field(default_factory=lambda:new_id("obligation")); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Obligation",organization_id=self.organization_id,actor_id=self.responsible_actor_id)

@dataclass
class Dependency:
    source_id:str; target_id:str; relationship_type:RelationshipType=RelationshipType.DEPENDS_ON; id:str=field(default_factory=lambda:new_id("dep")); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if self.source_id==self.target_id: raise InvariantViolation("An object cannot depend on itself.")
        if self.relationship_type not in {RelationshipType.DEPENDS_ON,RelationshipType.REQUIRES,RelationshipType.BLOCKS,RelationshipType.ENABLES}: raise InvariantViolation("Invalid dependency relationship type.")
        self.envelope=self.envelope or env(self.id,"Dependency")

@dataclass
class Relationship:
    source_id:str; target_id:str; relationship_type:RelationshipType; id:str=field(default_factory=lambda:new_id("rel")); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if self.source_id==self.target_id: raise InvariantViolation("A relationship cannot connect an object to itself.")
        self.envelope=self.envelope or env(self.id,"Relationship")

@dataclass
class Event:
    event_type:str; occurred_at:datetime; source:str; id:str=field(default_factory=lambda:new_id("event")); subject_id:Optional[str]=None; payload:dict[str,Any]=field(default_factory=dict); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Event")

@dataclass
class Evidence:
    description:str; source:str; occurred_at:datetime; id:str=field(default_factory=lambda:new_id("evidence")); subject_id:Optional[str]=None; authority_relationship:Optional[str]=None; reliability:Optional[str]=None; content_ref:Optional[str]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Evidence")

@dataclass
class Claim:
    proposition:str; id:str=field(default_factory=lambda:new_id("claim")); status:ClaimStatus=ClaimStatus.UNKNOWN; supporting_evidence_ids:list[str]=field(default_factory=list); contradicting_evidence_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        self.envelope=self.envelope or env(self.id,"Claim")
        if self.status==ClaimStatus.ESTABLISHED and not self.supporting_evidence_ids: raise InvariantViolation("ESTABLISHED claims require supporting evidence.")
        if self.status==ClaimStatus.CONFLICTED and not self.contradicting_evidence_ids: raise InvariantViolation("CONFLICTED claims require contradicting evidence.")

@dataclass
class TruthResolution:
    claim_id:str; resolved_status:ClaimStatus; resolution_basis:str; resolved_at:datetime; id:str=field(default_factory=lambda:new_id("truth")); supporting_evidence_ids:list[str]=field(default_factory=list); contradictory_evidence_ids:list[str]=field(default_factory=list); previous_resolution_id:Optional[str]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if self.resolved_status==ClaimStatus.ESTABLISHED and not self.supporting_evidence_ids: raise InvariantViolation("Established truth resolution requires supporting evidence.")
        self.envelope=self.envelope or env(self.id,"TruthResolution")

@dataclass
class State:
    subject_id:str; value:str; id:str=field(default_factory=lambda:new_id("state")); previous_state_id:Optional[str]=None; changed_at:datetime=field(default_factory=utcnow); actor_id:Optional[str]=None; cause:Optional[str]=None; evidence_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"State",actor_id=self.actor_id)

@dataclass
class Change:
    subject_id:str; from_value:str; to_value:str; changed_at:datetime; id:str=field(default_factory=lambda:new_id("change")); basis_evidence_ids:list[str]=field(default_factory=list); affected_object_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if self.from_value==self.to_value: raise InvariantViolation("A change must alter the represented value.")
        self.envelope=self.envelope or env(self.id,"Change")

@dataclass
class Consequence:
    change_id:str; affected_object_id:str; effect:str; causal_basis:str; support:ConsequenceSupport; id:str=field(default_factory=lambda:new_id("consequence")); evidence_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Consequence")

@dataclass
class SignificanceAssessment:
    consequence_id:str; significance:str; factors:list[str]; assessed_at:datetime; id:str=field(default_factory=lambda:new_id("significance")); uncertainty:Optional[str]=None; reversibility:Optional[str]=None; intervention_cost:Optional[str]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"SignificanceAssessment")

@dataclass
class Risk:
    description:str; severity:str; id:str=field(default_factory=lambda:new_id("risk")); related_object_ids:list[str]=field(default_factory=list); evidence_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Risk")

@dataclass
class Intervention:
    intervention_type:InterventionType; basis:str; id:str=field(default_factory=lambda:new_id("intervention")); target_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Intervention")

@dataclass
class Recommendation:
    proposal:str; basis:str; id:str=field(default_factory=lambda:new_id("recommendation")); intervention_id:Optional[str]=None; accepted:Optional[bool]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Recommendation")

@dataclass
class Decision:
    decision:str; decision_maker_id:str; authority_grant_id:str; decided_at:datetime; id:str=field(default_factory=lambda:new_id("decision")); rationale:Optional[str]=None; evidence_ids:list[str]=field(default_factory=list); affected_outcome_ids:list[str]=field(default_factory=list); supersedes_decision_id:Optional[str]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if not self.authority_grant_id: raise InvariantViolation("Consequential decisions require authority context.")
        self.envelope=self.envelope or env(self.id,"Decision",actor_id=self.decision_maker_id,authority_context_id=self.authority_grant_id)

@dataclass
class Permission:
    actor_id:str; operation:str; scope:str; id:str=field(default_factory=lambda:new_id("permission")); effective_from:Optional[datetime]=None; effective_until:Optional[datetime]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if self.effective_from and self.effective_from.tzinfo is None: raise InvariantViolation("Permission effective_from must be timezone-aware.")
        if self.effective_until and self.effective_until.tzinfo is None: raise InvariantViolation("Permission effective_until must be timezone-aware.")
        if self.effective_from and self.effective_until and self.effective_until < self.effective_from: raise InvariantViolation("Permission effective_until cannot precede effective_from.")
        self.envelope=self.envelope or env(self.id,"Permission",actor_id=self.actor_id,effective_at=self.effective_from,expires_at=self.effective_until)
    def is_active(self, at=None):
        at = at or utcnow()
        if at.tzinfo is None: raise InvariantViolation("Permission evaluation time must be timezone-aware.")
        return ((self.effective_from is None or at >= self.effective_from) and
                (self.effective_until is None or at <= self.effective_until))
    @property
    def active(self): return self.is_active()

@dataclass
class AuthorityGrant:
    grantor_id:str; recipient_id:str; scope:str; id:str=field(default_factory=lambda:new_id("authority")); effective_from:Optional[datetime]=None; effective_until:Optional[datetime]=None; limitations:list[str]=field(default_factory=list); revoked_at:Optional[datetime]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if self.grantor_id==self.recipient_id: raise InvariantViolation("Authority cannot be granted to the same actor as grantor.")
        if self.effective_from and self.effective_from.tzinfo is None: raise InvariantViolation("Authority effective_from must be timezone-aware.")
        if self.effective_until and self.effective_until.tzinfo is None: raise InvariantViolation("Authority effective_until must be timezone-aware.")
        if self.revoked_at and self.revoked_at.tzinfo is None: raise InvariantViolation("Authority revoked_at must be timezone-aware.")
        if self.effective_from and self.effective_until and self.effective_until < self.effective_from: raise InvariantViolation("Authority effective_until cannot precede effective_from.")
        if self.revoked_at and self.effective_from and self.revoked_at < self.effective_from: raise InvariantViolation("Authority cannot be revoked before becoming effective.")
        self.envelope=self.envelope or env(self.id,"AuthorityGrant",actor_id=self.grantor_id,effective_at=self.effective_from,expires_at=self.effective_until)
    def is_active(self, at=None):
        at = at or utcnow()
        if at.tzinfo is None:
            raise InvariantViolation("Authority grant evaluation time must be timezone-aware.")
        return (self.revoked_at is None and
                (self.effective_from is None or at >= self.effective_from) and
                (self.effective_until is None or at <= self.effective_until))
    @property
    def active(self): return self.is_active()

@dataclass
class Delegation:
    delegator_id:str; delegatee_id:str; scope:str; id:str=field(default_factory=lambda:new_id("delegation")); conditions:list[str]=field(default_factory=list); revoked_at:Optional[datetime]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if self.delegator_id==self.delegatee_id: raise InvariantViolation("An actor cannot delegate to itself.")
        self.envelope=self.envelope or env(self.id,"Delegation",actor_id=self.delegator_id)

@dataclass
class Authorization:
    actor_id:str; action_type:str; scope:str; authority_grant_id:str; authorized_by:str; id:str=field(default_factory=lambda:new_id("authz")); effective_from:Optional[datetime]=None; effective_until:Optional[datetime]=None; revoked_at:Optional[datetime]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if not self.authority_grant_id: raise InvariantViolation("Authorization requires an authority grant reference.")
        if self.effective_from and self.effective_from.tzinfo is None: raise InvariantViolation("Authorization effective_from must be timezone-aware.")
        if self.effective_until and self.effective_until.tzinfo is None: raise InvariantViolation("Authorization effective_until must be timezone-aware.")
        if self.revoked_at and self.revoked_at.tzinfo is None: raise InvariantViolation("Authorization revoked_at must be timezone-aware.")
        if self.effective_from and self.effective_until and self.effective_until < self.effective_from: raise InvariantViolation("Authorization effective_until cannot precede effective_from.")
        if self.revoked_at and self.effective_from and self.revoked_at < self.effective_from: raise InvariantViolation("Authorization cannot be revoked before becoming effective.")
        self.envelope=self.envelope or env(self.id,"Authorization",actor_id=self.authorized_by,effective_at=self.effective_from,expires_at=self.effective_until,authority_context_id=self.authority_grant_id)
    def is_active(self, at=None):
        at = at or utcnow()
        if at.tzinfo is None:
            raise InvariantViolation("Authorization evaluation time must be timezone-aware.")
        return (self.revoked_at is None and
                (self.effective_from is None or at >= self.effective_from) and
                (self.effective_until is None or at <= self.effective_until))
    @property
    def active(self): return self.is_active()

@dataclass
class Action:
    action_type:str; actor_id:str; target_id:str; authorization_id:str; id:str=field(default_factory=lambda:new_id("action")); status:ActionStatus=ActionStatus.PROPOSED; executed_at:Optional[datetime]=None; result:Optional[str]=None; envelope:Optional[ObjectEnvelope]=None
    def __setattr__(self, name, value):
        if name == "status" and getattr(self, "_lifecycle_initialized", False) and not getattr(self, "_lifecycle_mutation_allowed", False):
            raise LifecycleViolation("Action status is registry-managed; use transition().")
        object.__setattr__(self, name, value)
    def __post_init__(self):
        from .lifecycle import LIFECYCLE_REGISTRY
        definition = LIFECYCLE_REGISTRY["Action"]
        if self.status != definition.initial_state:
            raise InvariantViolation("Action construction must begin at the registered initial lifecycle state; use transition().")
        if not self.authorization_id: raise InvariantViolation("Consequential actions require authorization.")
        self.envelope=self.envelope or env(self.id,"Action",actor_id=self.actor_id)
        object.__setattr__(self, "_lifecycle_initialized", True)
        object.__setattr__(self, "_lifecycle_mutation_allowed", False)
    def transition(self,to_status:ActionStatus, *, actor_id=None, authority_context_id=None, evidence_ids=(), at=None, authority_objects=None, evidence_objects=None, organization_id=None, transaction_store=None):
        from .lifecycle import transition
        return transition(self, to_status, actor_id=actor_id, authority_context_id=authority_context_id, evidence_ids=tuple(evidence_ids), at=at, authority_objects=authority_objects, evidence_objects=evidence_objects, organization_id=organization_id, transaction_store=transaction_store)

@dataclass
class ObservedResponse:
    action_id:str; observation:str; observed_at:datetime; id:str=field(default_factory=lambda:new_id("response")); evidence_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"ObservedResponse")

@dataclass
class Validation:
    target_condition_id:str; validator_id:str; method:str; result:ValidationResult; validated_at:datetime; id:str=field(default_factory=lambda:new_id("validation")); evidence_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if self.result==ValidationResult.SATISFIED and not self.evidence_ids: raise InvariantViolation("Satisfied validation requires evidence.")
        self.envelope=self.envelope or env(self.id,"Validation",actor_id=self.validator_id)

@dataclass
class Recovery:
    description:str; target_id:str; evaluated_against_outcome_id:str; id:str=field(default_factory=lambda:new_id("recovery")); evidence_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Recovery")

@dataclass
class Notification:
    recipient_id:str; message:str; id:str=field(default_factory=lambda:new_id("notification")); related_object_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Notification")

@dataclass
class Meeting:
    title:str; starts_at:datetime; id:str=field(default_factory=lambda:new_id("meeting")); ends_at:Optional[datetime]=None; participant_ids:list[str]=field(default_factory=list); operational_thread_id:Optional[str]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if self.ends_at and self.ends_at<self.starts_at: raise InvariantViolation("Meeting end cannot precede start.")
        self.envelope=self.envelope or env(self.id,"Meeting")

@dataclass
class Artifact:
    name:str; source:str; id:str=field(default_factory=lambda:new_id("artifact")); content_ref:Optional[str]=None; evidence_ids:list[str]=field(default_factory=list); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"Artifact")

@dataclass
class HistoryRecord:
    subject_id:str; event_type:str; occurred_at:datetime; id:str=field(default_factory=lambda:new_id("history")); actor_id:Optional[str]=None; prior_state:Optional[str]=None; resulting_state:Optional[str]=None; evidence_ids:list[str]=field(default_factory=list); trace_id:Optional[str]=None; correction_id:Optional[str]=None; supersession_id:Optional[str]=None; envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"HistoryRecord",actor_id=self.actor_id,trace_ref=self.trace_id)

@dataclass
class Correction:
    subject_id:str; before_reference:str; after_reference:str; reason:str; corrected_at:datetime; id:str=field(default_factory=lambda:new_id("correction")); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if self.before_reference==self.after_reference: raise InvariantViolation("A correction must change the referenced representation.")
        self.envelope=self.envelope or env(self.id,"Correction")

@dataclass
class Supersession:
    previous_id:str; successor_id:str; reason:str; superseded_at:datetime; id:str=field(default_factory=lambda:new_id("supersession")); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        if self.previous_id==self.successor_id: raise InvariantViolation("An object cannot supersede itself.")
        if self.superseded_at.tzinfo is None: raise InvariantViolation("Supersession time must be timezone-aware.")
        self.envelope=self.envelope or env(self.id,"Supersession")
    @staticmethod
    def apply(previous, successor, supersession):
        # An execution method is itself a constitutional boundary. It must not rely
        # on callers having run validate_all() first, because that would permit an
        # invalid state transition through a lower-level mutation API.
        if previous.id != supersession.previous_id or successor.id != supersession.successor_id:
            raise InvariantViolation("Supersession references do not match the supplied objects.")
        if type(previous) is not type(successor):
            raise InvariantViolation("Supersession must connect objects of the same canonical type.")
        if previous.envelope.validity_status == ValidityStatus.SUPERSEDED:
            raise InvariantViolation("A superseded object cannot be superseded again through the mutation API.")
        if successor.envelope.validity_status == ValidityStatus.SUPERSEDED:
            raise InvariantViolation("A superseded object cannot become the active successor.")
        previous_org = getattr(getattr(previous, "envelope", None), "organization_id", None)
        successor_org = getattr(getattr(successor, "envelope", None), "organization_id", None)
        supersession_org = getattr(getattr(supersession, "envelope", None), "organization_id", None)
        scoped = (previous_org, successor_org, supersession_org)
        scoped_orgs = {org for org in scoped if org is not None}
        if scoped_orgs and any(org is None for org in scoped):
            raise InvariantViolation("Supersession involving a tenant-scoped object requires tenant context on every lineage object.")
        if len(scoped_orgs) > 1:
            raise InvariantViolation("Supersession cannot cross organization boundaries.")
        if previous.id == successor.id:
            raise InvariantViolation("An object cannot supersede itself.")
        if successor.envelope.created_at < previous.envelope.created_at:
            raise InvariantViolation("Supersession successor cannot predate its predecessor.")
        if supersession.superseded_at < successor.envelope.created_at:
            raise InvariantViolation("Supersession cannot be recorded before its successor exists.")
        # Validate every condition before mutating the predecessor. Failed application
        # must be atomic: an invalid supersession cannot partially rewrite current state.
        previous.envelope=ObjectEnvelope(**{**previous.envelope.__dict__, "validity_status": ValidityStatus.SUPERSEDED})
        return supersession

@dataclass
class ProcessingTrace:
    input_ref:str; id:str=field(default_factory=lambda:new_id("trace")); stages:list[str]=field(default_factory=list); skipped_stages:list[str]=field(default_factory=list); final_state_ref:Optional[str]=None; envelope:Optional[ObjectEnvelope]=None
    REQUIRED_ORDER=("INPUT","IDENTITY","EVIDENCE","TRUTH","TEMPORAL","CHANGE","CONSEQUENCE","SIGNIFICANCE","RESPONSE","PERMISSION","AUTHORITY","AUTHORIZATION","ACTION","OBSERVATION","VALIDATION","FINAL_STATE")
    def __post_init__(self): self.envelope=self.envelope or env(self.id,"ProcessingTrace",trace_ref=self.id)
    def validate(self):
        idx=[]
        for s in self.stages:
            if s not in self.REQUIRED_ORDER: raise InvariantViolation(f"Unknown trace stage: {s}")
            idx.append(self.REQUIRED_ORDER.index(s))
        if idx!=sorted(idx) or len(idx)!=len(set(idx)): raise InvariantViolation("Trace stages must preserve constitutional order and uniqueness.")
        skipped_idx=[]
        for s in self.skipped_stages:
            if s not in self.REQUIRED_ORDER: raise InvariantViolation(f"Unknown skipped trace stage: {s}")
            if s in self.stages: raise InvariantViolation("A trace stage cannot be both executed and skipped.")
            skipped_idx.append(self.REQUIRED_ORDER.index(s))
        if len(skipped_idx)!=len(set(skipped_idx)): raise InvariantViolation("Skipped trace stages must be unique.")
        if self.final_state_ref and "FINAL_STATE" not in self.stages: raise InvariantViolation("A final_state_ref requires FINAL_STATE trace stage.")

@dataclass
class ExecutionProofRecord:
    execution_id:str; engine_version:str; fixture_version:str; test_id:str; test_version:str; input_hash:str; output_hash:str; oracle_result:str; environment:str; schema_version:str=SCHEMA_VERSION; run_version:str="1.0"; id:str=field(default_factory=lambda:new_id("proof")); trace_id:Optional[str]=None; regression_status:Optional[str]=None; executed_at:datetime=field(default_factory=utcnow); envelope:Optional[ObjectEnvelope]=None
    def __post_init__(self):
        required=(self.execution_id,self.engine_version,self.fixture_version,self.test_id,self.test_version,self.input_hash,self.output_hash,self.oracle_result,self.environment)
        if any(not x for x in required): raise InvariantViolation("Execution proof requires complete attribution.")
        self.envelope=self.envelope or env(self.id,"ExecutionProofRecord",trace_ref=self.trace_id)
