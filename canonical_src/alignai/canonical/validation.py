from datetime import datetime
from dataclasses import fields, is_dataclass, replace
from .models import *
from .errors import InvariantViolation
from .relationships import assert_relationship

def _require_aware(value, label):
    if value is not None and isinstance(value, datetime) and value.tzinfo is None:
        raise InvariantViolation(f"{label} must be timezone-aware.")


def _require_reference(obj, field_name, objects_by_id, expected_type=None):
    value = getattr(obj, field_name)
    if value is None:
        return
    if value not in objects_by_id:
        raise InvariantViolation(
            f"{type(obj).__name__}.{field_name} references unknown canonical object {value!r}."
        )
    if expected_type is not None and not isinstance(objects_by_id[value], expected_type):
        raise InvariantViolation(
            f"{type(obj).__name__}.{field_name} must reference {expected_type.__name__}, "
            f"not {type(objects_by_id[value]).__name__}."
        )


def _require_references(obj, field_name, objects_by_id, expected_type=None):
    for value in getattr(obj, field_name):
        if value not in objects_by_id:
            raise InvariantViolation(
                f"{type(obj).__name__}.{field_name} references unknown canonical object {value!r}."
            )
        if expected_type is not None and not isinstance(objects_by_id[value], expected_type):
            raise InvariantViolation(
                f"{type(obj).__name__}.{field_name} must reference {expected_type.__name__}, "
                f"not {type(objects_by_id[value]).__name__}."
            )


def _organization_id(obj):
    """Return canonical tenant context when present."""
    envelope = getattr(obj, "envelope", None)
    return getattr(envelope, "organization_id", None) if envelope is not None else None


def _require_same_organization(obj, referenced, field_name):
    source_org = _organization_id(obj)
    target_org = _organization_id(referenced)
    if source_org is not None and target_org is not None and source_org != target_org:
        raise InvariantViolation(
            f"{type(obj).__name__}.{field_name} crosses organization boundary "
            f"from {source_org!r} to {target_org!r}."
        )


def _enforce_reference_tenant_consistency(obj, referenced_objects):
    """Ensure an object cannot hide or contradict tenant context through references.

    A reference to a tenant-scoped object makes the referring object operationally
    tenant-scoped too. If several referenced objects are scoped, they must agree.
    An explicitly scoped referring object must agree with every scoped reference.
    This closes the bypass where an unscoped wrapper (e.g. Action/Authorization)
    connected objects from different organizations while structural references still
    looked valid.
    """
    referenced_orgs = {org for _, referenced in referenced_objects
                       if (org := _organization_id(referenced)) is not None}
    if not referenced_orgs:
        return
    if len(referenced_orgs) > 1:
        raise InvariantViolation(
            f"{type(obj).__name__} references objects from multiple organization boundaries."
        )
    object_org = _organization_id(obj)
    referenced_org = next(iter(referenced_orgs))
    # Some canonical objects are intentionally unscoped wrappers. They may refer
    # into one tenant, but they must never bridge two tenant contexts.
    if object_org is None:
        return
    if object_org != referenced_org:
        raise InvariantViolation(
            f"{type(obj).__name__} organization context must match its tenant-scoped references."
        )


def validate_object(obj):
    # Canonical temporal fields are a class-wide invariant, not a handful of
    # object-specific checks. Any datetime field on a canonical dataclass must
    # carry explicit timezone information so validation cannot depend on the
    # machine's local timezone.
    if is_dataclass(obj):
        for field_info in fields(obj):
            value = getattr(obj, field_info.name)
            if isinstance(value, datetime):
                _require_aware(value, f"{type(obj).__name__}.{field_info.name}")
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, datetime):
                        _require_aware(item, f"{type(obj).__name__}.{field_info.name}")

    env = getattr(obj, "envelope", None)
    if not isinstance(env, ObjectEnvelope):
        raise InvariantViolation(f"{type(obj).__name__} requires a canonical envelope.")
    # Organization context is a constitutional identity boundary. Any canonical
    # object with an explicit organization_id must agree with its envelope, and
    # an Organization envelope must identify the organization itself. Otherwise
    # different engine paths can observe contradictory tenant ownership.
    if hasattr(obj, "organization_id"):
        domain_org = getattr(obj, "organization_id")
        if domain_org is None:
            raise InvariantViolation(f"{type(obj).__name__}.organization_id cannot be null.")
        if env.organization_id != domain_org:
            raise InvariantViolation(f"{type(obj).__name__} organization context must match its envelope.")
    if isinstance(obj, Organization) and env.organization_id != obj.id:
        raise InvariantViolation("Organization envelope organization_id must equal organization ID.")
    if env.id != obj.id:
        raise InvariantViolation("Envelope ID must equal object ID.")
    if env.object_type != type(obj).__name__:
        raise InvariantViolation("Envelope object_type must equal concrete object type.")
    if env.object_version < 1:
        raise InvariantViolation("Object version must be >= 1.")
    if env.schema_version != SCHEMA_VERSION:
        raise InvariantViolation(
            f"Canonical Data Model v{SCHEMA_VERSION} requires schema_version {SCHEMA_VERSION!r}, "
            f"not {env.schema_version!r}."
        )
    if isinstance(obj, OperationalThread):
        from .lifecycle import LIFECYCLE_REGISTRY
        lifecycle_definition = LIFECYCLE_REGISTRY["OperationalThread"]
        if obj.envelope.lifecycle_state not in lifecycle_definition.allowed_states:
            raise InvariantViolation("OperationalThread lifecycle state is outside the registered lifecycle vocabulary.")
        if obj.envelope.lifecycle_state not in lifecycle_definition.transitions and obj.envelope.lifecycle_state not in lifecycle_definition.terminal_states:
            raise InvariantViolation("OperationalThread lifecycle state is not registered.")
    if isinstance(obj, WorkItem):
        from .lifecycle import LIFECYCLE_REGISTRY
        lifecycle_definition = LIFECYCLE_REGISTRY["WorkItem"]
        if obj.lifecycle_state not in lifecycle_definition.allowed_states:
            raise InvariantViolation("WorkItem lifecycle state is outside the registered lifecycle vocabulary.")
        if obj.envelope.lifecycle_state not in lifecycle_definition.allowed_states:
            raise InvariantViolation("WorkItem envelope lifecycle state is outside the registered lifecycle vocabulary.")
        if obj.envelope.lifecycle_state != obj.lifecycle_state:
            raise InvariantViolation("WorkItem lifecycle state and envelope lifecycle state must agree.")
        if obj.lifecycle_state.value == "COMPLETED" and obj.actual_completion is None:
            raise InvariantViolation("Completed work requires actual_completion.")
        if obj.lifecycle_state.value != "COMPLETED" and obj.actual_completion is not None:
            raise InvariantViolation("Non-completed work cannot carry an actual_completion timestamp.")
    if isinstance(obj, Claim):
        if obj.status.value == "ESTABLISHED" and not obj.supporting_evidence_ids:
            raise InvariantViolation("Established claim requires supporting evidence.")
        if obj.status.value == "CONFLICTED" and not obj.contradicting_evidence_ids:
            raise InvariantViolation("Conflicted claim requires contradicting evidence.")
    if isinstance(obj, TruthResolution):
        if obj.resolved_status.value == "ESTABLISHED" and not obj.supporting_evidence_ids:
            raise InvariantViolation("Established truth resolution requires supporting evidence.")
        if obj.resolved_status.value == "CONFLICTED" and not obj.contradictory_evidence_ids:
            raise InvariantViolation("Conflicted truth resolution requires contradictory evidence.")
    if isinstance(obj, Validation) and obj.result.value == "SATISFIED" and not obj.evidence_ids:
        raise InvariantViolation("Satisfied validation requires evidence.")
    if isinstance(obj, SuccessCondition) and obj.satisfied and not obj.validation_ids:
        raise InvariantViolation("Satisfied success condition requires validation.")
    if isinstance(obj, Decision) and not obj.authority_grant_id:
        raise InvariantViolation("Decision requires authority context.")
    if isinstance(obj, Action):
        if not obj.authorization_id:
            raise InvariantViolation("Action requires authorization.")
        if obj.status.value == "EXECUTED" and obj.executed_at is None:
            raise InvariantViolation("Executed action requires executed_at.")
        if obj.status.value != "EXECUTED" and obj.executed_at is not None:
            raise InvariantViolation("Only an executed action may carry executed_at.")
    if isinstance(obj, Permission) and not obj.actor_id:
        raise InvariantViolation("Permission requires actor identity.")
    if isinstance(obj, Permission):
        if obj.envelope.effective_at != obj.effective_from or obj.envelope.expires_at != obj.effective_until:
            raise InvariantViolation("Permission temporal fields must match their canonical envelope.")
    if isinstance(obj, AuthorityGrant) and obj.grantor_id == obj.recipient_id:
        raise InvariantViolation("Authority grant cannot be self-granted.")
    if isinstance(obj, AuthorityGrant):
        if obj.envelope.effective_at != obj.effective_from or obj.envelope.expires_at != obj.effective_until:
            raise InvariantViolation("Authority grant temporal fields must match their canonical envelope.")
    if isinstance(obj, Delegation) and obj.delegator_id == obj.delegatee_id:
        raise InvariantViolation("Delegation cannot be self-delegated.")
    if isinstance(obj, Authorization) and not obj.authority_grant_id:
        raise InvariantViolation("Authorization requires authority grant.")
    if isinstance(obj, Authorization):
        if obj.envelope.effective_at != obj.effective_from or obj.envelope.expires_at != obj.effective_until:
            raise InvariantViolation("Authorization temporal fields must match their canonical envelope.")
    if isinstance(obj, Meeting) and obj.ends_at and obj.ends_at < obj.starts_at:
        raise InvariantViolation("Meeting end precedes start.")
    if isinstance(obj, Change) and obj.from_value == obj.to_value:
        raise InvariantViolation("Change must alter value.")
    if isinstance(obj, Correction) and obj.before_reference == obj.after_reference:
        raise InvariantViolation("Correction must change reference.")
    if isinstance(obj, Supersession) and obj.previous_id == obj.successor_id:
        raise InvariantViolation("An object cannot supersede itself.")
    if isinstance(obj, ProcessingTrace):
        obj.validate()


def validate_all(objects):
    objects_by_id = {}
    for obj in objects:
        validate_object(obj)
        if obj.id in objects_by_id:
            raise InvariantViolation(f"Duplicate canonical object ID: {obj.id!r}.")
        objects_by_id[obj.id] = obj

    reference_rules = {
        Person: [("organization_id", Organization), ("role_ids", Role), ("permission_ids", Permission)],
        Role: [("organization_id", Organization)],
        IntendedOutcome: [("organization_id", Organization), ("success_condition_ids", SuccessCondition), ("owner_id", Person)],
        SuccessCondition: [("outcome_id", IntendedOutcome), ("validation_ids", Validation)],
        OperationalThread: [("organization_id", Organization),
            ("intended_outcome_id", IntendedOutcome),
            ("success_condition_ids", SuccessCondition),
            ("participant_ids", Person),
            ("responsibility_ids", Responsibility),
            ("work_item_ids", WorkItem),
            ("commitment_ids", Commitment),
            ("obligation_ids", Obligation),
            ("dependency_ids", Dependency),
            ("evidence_ids", Evidence),
            ("claim_ids", Claim),
            ("decision_ids", Decision),
            ("intervention_ids", Intervention),
            ("validation_ids", Validation),
        ],
        Responsibility: [("organization_id", Organization), ("person_id", Person)],
        WorkItem: [("organization_id", Organization),
            ("outcome_id", IntendedOutcome),
            ("owner_id", Person),
            ("assignee_id", Person),
            ("evidence_ids", Evidence),
            ("dependency_ids", Dependency),
        ],
        Commitment: [("organization_id", Organization), ("actor_id", Person)],
        Obligation: [("organization_id", Organization), ("responsible_actor_id", Person)],
        Dependency: [("source_id", None), ("target_id", None)],
        Relationship: [("source_id", None), ("target_id", None)],
        Event: [("subject_id", None)],
        Evidence: [("subject_id", None)],
        Claim: [("supporting_evidence_ids", Evidence), ("contradicting_evidence_ids", Evidence)],
        TruthResolution: [
            ("claim_id", Claim),
            ("supporting_evidence_ids", Evidence),
            ("contradictory_evidence_ids", Evidence),
            ("previous_resolution_id", None),
        ],
        State: [("subject_id", None), ("previous_state_id", State), ("actor_id", Person), ("evidence_ids", Evidence)],
        Change: [("subject_id", None), ("basis_evidence_ids", Evidence), ("affected_object_ids", None)],
        Consequence: [("change_id", Change), ("affected_object_id", None), ("evidence_ids", Evidence)],
        SignificanceAssessment: [("consequence_id", Consequence)],
        Risk: [("related_object_ids", None), ("evidence_ids", Evidence)],
        Intervention: [("target_ids", None)],
        Recommendation: [("intervention_id", Intervention)],
        Decision: [
            ("decision_maker_id", Person),
            ("authority_grant_id", AuthorityGrant),
            ("evidence_ids", Evidence),
            ("affected_outcome_ids", IntendedOutcome),
            ("supersedes_decision_id", Decision),
        ],
        Permission: [("actor_id", Person)],
        AuthorityGrant: [("grantor_id", Person), ("recipient_id", Person)],
        Delegation: [("delegator_id", Person), ("delegatee_id", Person)],
        Authorization: [("actor_id", Person), ("authority_grant_id", AuthorityGrant), ("authorized_by", Person)],
        Action: [("actor_id", Person), ("authorization_id", Authorization)],
        ObservedResponse: [("action_id", Action), ("evidence_ids", Evidence)],
        Validation: [("target_condition_id", SuccessCondition), ("validator_id", Person), ("evidence_ids", Evidence)],
        Recovery: [("target_id", None), ("evaluated_against_outcome_id", IntendedOutcome), ("evidence_ids", Evidence)],
        Notification: [("recipient_id", Person), ("related_object_ids", None)],
        Meeting: [("participant_ids", Person), ("operational_thread_id", OperationalThread)],
        Artifact: [("evidence_ids", Evidence)],
        HistoryRecord: [
            ("subject_id", None),
            ("actor_id", Person),
            ("evidence_ids", Evidence),
            ("trace_id", ProcessingTrace),
            ("correction_id", Correction),
            ("supersession_id", Supersession),
        ],
        Correction: [("subject_id", None)],
        Supersession: [("previous_id", None), ("successor_id", None)],
        ExecutionProofRecord: [("trace_id", ProcessingTrace)],
        ProcessingTrace: [("input_ref", None), ("final_state_ref", None)],
    }

    supersession_successors = {}
    correction_edges = {}
    state_predecessors = {}
    state_successors = {}
    truth_resolution_predecessors = {}
    truth_resolution_successors = {}

    for obj in objects:
        for field_name, expected_type in reference_rules.get(type(obj), []):
            value = getattr(obj, field_name)
            if isinstance(value, list):
                _require_references(obj, field_name, objects_by_id, expected_type)
                for reference_id in value:
                    _require_same_organization(obj, objects_by_id[reference_id], field_name)
            else:
                _require_reference(obj, field_name, objects_by_id, expected_type)
                if value is not None:
                    _require_same_organization(obj, objects_by_id[value], field_name)

        referenced_objects = []
        for field_name, expected_type in reference_rules.get(type(obj), []):
            value = getattr(obj, field_name)
            if isinstance(value, list):
                referenced_objects.extend((field_name, objects_by_id[reference_id]) for reference_id in value)
            elif value is not None and value in objects_by_id:
                referenced_objects.append((field_name, objects_by_id[value]))
        _enforce_reference_tenant_consistency(obj, referenced_objects)

        if isinstance(obj, SuccessCondition) and obj.satisfied:
            validations = [objects_by_id[reference_id] for reference_id in obj.validation_ids]
            if not any(validation.result == ValidationResult.SATISFIED for validation in validations):
                raise InvariantViolation("A satisfied SuccessCondition requires at least one SATISFIED validation.")

        if isinstance(obj, ProcessingTrace):
            obj.validate()

        if isinstance(obj, Decision):
            grant = objects_by_id[obj.authority_grant_id]
            if grant.recipient_id != obj.decision_maker_id:
                raise InvariantViolation("Decision maker must be the recipient of the cited authority grant.")

        if isinstance(obj, Authorization):
            grant = objects_by_id[obj.authority_grant_id]
            if grant.recipient_id != obj.actor_id:
                raise InvariantViolation("Authorization actor must be the recipient of the cited authority grant.")
            if grant.grantor_id != obj.authorized_by:
                raise InvariantViolation("Authorization authorized_by must match the authority grantor.")
            if obj.effective_from is not None and grant.effective_from is not None and obj.effective_from < grant.effective_from:
                raise InvariantViolation("Authorization cannot become effective before its authority grant.")
            if obj.effective_until is not None and grant.effective_until is not None and obj.effective_until > grant.effective_until:
                raise InvariantViolation("Authorization cannot remain effective after its authority grant expires.")
            if grant.revoked_at is not None:
                if obj.effective_from is not None and obj.effective_from >= grant.revoked_at:
                    raise InvariantViolation("Authorization cannot become effective after its authority grant was revoked.")
                if obj.effective_until is None or obj.effective_until > grant.revoked_at:
                    raise InvariantViolation("Authorization cannot remain effective after its authority grant was revoked.")

        if isinstance(obj, Action):
            authorization = objects_by_id[obj.authorization_id]
            if authorization.actor_id != obj.actor_id:
                raise InvariantViolation("Action actor must match the actor named by its authorization.")
            if authorization.action_type != obj.action_type:
                raise InvariantViolation("Action type must match the authorized action type.")
            if obj.status.value == "EXECUTED" and obj.executed_at is not None:
                if not authorization.is_active(obj.executed_at):
                    raise InvariantViolation("Executed action must occur while its authorization is active.")

        if isinstance(obj, Relationship):
            source = objects_by_id[obj.source_id]
            target = objects_by_id[obj.target_id]
            _require_same_organization(obj, source, "source_id")
            _require_same_organization(obj, target, "target_id")
            if _organization_id(source) is not None and _organization_id(target) is not None and _organization_id(source) != _organization_id(target):
                raise InvariantViolation("Relationship cannot cross organization boundaries.")
            assert_relationship(type(source).__name__, type(target).__name__, obj.relationship_type)

        if isinstance(obj, Dependency):
            source = objects_by_id[obj.source_id]
            target = objects_by_id[obj.target_id]
            dependency_org = _organization_id(obj)
            source_org = _organization_id(source)
            target_org = _organization_id(target)

            # A dependency is an operational edge, not an unscoped relationship.
            # Its tenant must be explicit and must agree with both endpoints.
            # Otherwise an endpoint can be made unscoped (or the dependency itself
            # can lose its tenant) and the edge becomes ambiguous while still
            # passing structural validation.
            if dependency_org is None:
                raise InvariantViolation("Dependency requires explicit organization context.")
            if source_org is None:
                raise InvariantViolation("Dependency source must have explicit organization context.")
            if target_org is None:
                raise InvariantViolation("Dependency target must have explicit organization context.")
            if dependency_org != source_org or dependency_org != target_org:
                raise InvariantViolation("Dependency organization context must match both endpoints.")
            assert_relationship(type(source).__name__, type(target).__name__, obj.relationship_type)

        if isinstance(obj, TruthResolution):
            if obj.previous_resolution_id is not None:
                previous = objects_by_id.get(obj.previous_resolution_id)
                if previous is None:
                    raise InvariantViolation("TruthResolution previous_resolution_id references an unknown TruthResolution.")
                if not isinstance(previous, TruthResolution):
                    raise InvariantViolation("TruthResolution previous_resolution_id must reference a TruthResolution.")
                if previous.claim_id != obj.claim_id:
                    raise InvariantViolation("Truth resolution lineage must remain within the same claim.")
                if previous.id == obj.id:
                    raise InvariantViolation("A TruthResolution cannot reference itself as its previous resolution.")
                if previous.resolved_at > obj.resolved_at:
                    raise InvariantViolation("A TruthResolution cannot occur before its previous resolution.")
                existing_successor = truth_resolution_successors.get(previous.id)
                if existing_successor is not None and existing_successor != obj.id:
                    raise InvariantViolation("A TruthResolution predecessor cannot have competing successors.")
                truth_resolution_successors[previous.id] = obj.id
                truth_resolution_predecessors[obj.id] = previous.id

        if isinstance(obj, State):
            if obj.previous_state_id is not None:
                previous = objects_by_id.get(obj.previous_state_id)
                if previous is None:
                    raise InvariantViolation("State previous_state_id references an unknown State.")
                if not isinstance(previous, State):
                    raise InvariantViolation("State previous_state_id must reference a State.")
                if previous.subject_id != obj.subject_id:
                    raise InvariantViolation("State lineage must remain within the same subject.")
                if previous.id == obj.id:
                    raise InvariantViolation("A State cannot reference itself as its previous state.")
                if previous.changed_at > obj.changed_at:
                    raise InvariantViolation("A State cannot occur before its previous state.")
                existing_successor = state_successors.get(previous.id)
                if existing_successor is not None and existing_successor != obj.id:
                    raise InvariantViolation("A State predecessor cannot have competing successors.")
                state_successors[previous.id] = obj.id
                state_predecessors[obj.id] = previous.id

        if isinstance(obj, HistoryRecord):
            # History event type must agree with the lineage object it claims to record.
            # Otherwise a record can carry a correction/supersession reference while
            # describing a different event, making reconstruction ambiguous.
            if obj.event_type == "CORRECTION" and not obj.correction_id:
                raise InvariantViolation("CORRECTION history requires a correction reference.")
            if obj.event_type == "SUPERSESSION" and not obj.supersession_id:
                raise InvariantViolation("SUPERSESSION history requires a supersession reference.")
            if obj.correction_id and obj.event_type != "CORRECTION":
                raise InvariantViolation("Correction linkage requires CORRECTION history event type.")
            if obj.supersession_id and obj.event_type != "SUPERSESSION":
                raise InvariantViolation("Supersession linkage requires SUPERSESSION history event type.")
            subject = objects_by_id[obj.subject_id]
            if (obj.prior_state is None) != (obj.resulting_state is None):
                raise InvariantViolation("A history state transition must identify both prior and resulting states.")
            if obj.prior_state is not None:
                if str(obj.event_type).startswith("LIFECYCLE:"):
                    # Lifecycle HistoryRecord state values are Registry enum values,
                    # not references to canonical State objects. Canonical State
                    # history remains a separate constitutional mechanism.
                    if not isinstance(obj.prior_state, str) or not isinstance(obj.resulting_state, str):
                        raise InvariantViolation("Lifecycle history states must be canonical string state values.")
                else:
                    _require_reference(obj, "prior_state", objects_by_id, State)
                    _require_reference(obj, "resulting_state", objects_by_id, State)
                    prior = objects_by_id[obj.prior_state]
                    resulting = objects_by_id[obj.resulting_state]
                    if not isinstance(prior, State) or not isinstance(resulting, State):
                        raise InvariantViolation("History state references must point to State objects.")
                    if prior.subject_id != obj.subject_id or resulting.subject_id != obj.subject_id:
                        raise InvariantViolation("History states must belong to the recorded subject.")
                    if prior.id == resulting.id:
                        raise InvariantViolation("A history state transition must actually change state.")
                    if resulting.previous_state_id != prior.id:
                        raise InvariantViolation("History state transition must match the resulting state's previous state lineage.")
                    if prior.changed_at > obj.occurred_at or resulting.changed_at > obj.occurred_at:
                        raise InvariantViolation("History cannot record a state transition before the referenced states occurred.")
                    if not obj.evidence_ids and not obj.trace_id:
                        raise InvariantViolation("Consequential history requires evidence or a processing trace.")
            if obj.event_type == "STATE_CHANGE" and obj.prior_state is None:
                raise InvariantViolation("STATE_CHANGE history requires prior and resulting state references.")
            if obj.correction_id:
                correction = objects_by_id[obj.correction_id]
                if correction.subject_id != obj.subject_id:
                    raise InvariantViolation("History correction linkage must refer to the same subject.")
                if obj.occurred_at < correction.corrected_at:
                    raise InvariantViolation("History correction event cannot precede correction time.")
            if obj.supersession_id:
                supersession = objects_by_id[obj.supersession_id]
                if obj.subject_id not in (supersession.previous_id, supersession.successor_id):
                    raise InvariantViolation("History supersession linkage must refer to the superseded lineage.")
                if obj.occurred_at < supersession.superseded_at:
                    raise InvariantViolation("History supersession event cannot precede supersession time.")

        if isinstance(obj, Correction):
            _require_reference(obj, "before_reference", objects_by_id)
            _require_reference(obj, "after_reference", objects_by_id)
            before = objects_by_id[obj.before_reference]
            after = objects_by_id[obj.after_reference]
            subject = objects_by_id.get(obj.subject_id)
            if subject is None:
                raise InvariantViolation("Correction subject must reference an existing canonical object.")
            correction_orgs = {org for candidate in (subject, before, after)
                               if (org := _organization_id(candidate)) is not None}
            if len(correction_orgs) > 1:
                raise InvariantViolation("Correction cannot cross organization boundaries.")
            correction_org = _organization_id(obj)
            if correction_org is not None and correction_orgs and correction_org not in correction_orgs:
                raise InvariantViolation("Correction organization context must match its corrected subject representations.")
            if type(before) is not type(after):
                raise InvariantViolation("Correction before/after representations must have the same canonical type.")
            if type(subject) is not type(before):
                raise InvariantViolation("Correction subject type must match corrected representations.")
            if before.id == after.id:
                raise InvariantViolation("Correction must reference distinct representations.")
            if after.envelope.created_at < before.envelope.created_at:
                raise InvariantViolation("Correction successor representation cannot predate its predecessor.")
            if obj.corrected_at < before.envelope.created_at:
                raise InvariantViolation("Correction cannot be recorded before the original representation exists.")
            if obj.corrected_at < after.envelope.created_at:
                raise InvariantViolation("Correction cannot be recorded before the corrected representation exists.")
            existing_correction_successor = correction_edges.get(before.id)
            if existing_correction_successor is not None and existing_correction_successor != after.id:
                raise InvariantViolation("A correction predecessor cannot have competing successors.")
            correction_edges[before.id] = after.id

        if isinstance(obj, Supersession):
            previous = objects_by_id[obj.previous_id]
            successor = objects_by_id[obj.successor_id]
            if type(previous) is not type(successor):
                raise InvariantViolation("Supersession must connect objects of the same canonical type.")
            existing_successor = supersession_successors.get(previous.id)
            if existing_successor is not None and existing_successor != successor.id:
                raise InvariantViolation("A supersession predecessor cannot have competing successors.")
            supersession_successors[previous.id] = successor.id
            if successor.envelope.created_at < previous.envelope.created_at:
                raise InvariantViolation("Supersession successor cannot predate its predecessor.")
            if obj.superseded_at < successor.envelope.created_at:
                raise InvariantViolation("Supersession cannot be recorded before its successor exists.")
            if previous.envelope.validity_status != ValidityStatus.SUPERSEDED:
                raise InvariantViolation("A superseded predecessor must be marked SUPERSEDED.")
            if successor.envelope.validity_status == ValidityStatus.SUPERSEDED:
                raise InvariantViolation("A supersession successor cannot already be SUPERSEDED.")

    # Resolve tenant context transitively through canonical references. An
    # intentionally unscoped wrapper may inherit one tenant from its references,
    # but it must never become a hidden bridge between multiple tenants. This is
    # stronger than checking only the immediate envelope of a reference.
    tenant_memo = {}
    tenant_visiting = set()

    def effective_org(obj_id):
        if obj_id in tenant_memo:
            return tenant_memo[obj_id]
        if obj_id in tenant_visiting:
            # Cycles are handled by the relevant lineage/reference invariants;
            # do not manufacture tenant context from a recursive loop.
            return _organization_id(objects_by_id[obj_id])
        tenant_visiting.add(obj_id)
        obj = objects_by_id[obj_id]
        orgs = set()
        own_org = _organization_id(obj)
        if own_org is not None:
            orgs.add(own_org)
        for field_name, _expected_type in reference_rules.get(type(obj), []):
            value = getattr(obj, field_name)
            refs = value if isinstance(value, list) else ([value] if value is not None else [])
            for ref_id in refs:
                if ref_id in objects_by_id:
                    ref_org = effective_org(ref_id)
                    if ref_org is not None:
                        orgs.add(ref_org)
        tenant_visiting.remove(obj_id)
        if len(orgs) > 1:
            raise InvariantViolation(f"{type(obj).__name__} has conflicting transitive organization context.")
        resolved = next(iter(orgs), None)
        tenant_memo[obj_id] = resolved
        return resolved

    for object_id in objects_by_id:
        effective_org(object_id)


    # Truth-resolution lineage is a directed evidence-resolution history. It must
    # remain acyclic and claim-local so the engine can reconstruct how truth status
    # evolved without mixing claims or creating circular resolution history.
    for start in truth_resolution_predecessors:
        seen = set()
        current = start
        while current in truth_resolution_predecessors:
            if current in seen:
                raise InvariantViolation("Truth resolution lineage must be acyclic.")
            seen.add(current)
            current = truth_resolution_predecessors[current]

    # State lineage is also a directed historical graph. It must remain acyclic so
    # current state can always be reconstructed without circular history.
    for start in state_predecessors:
        seen = set()
        current = start
        while current in state_predecessors:
            if current in seen:
                raise InvariantViolation("State lineage must be acyclic.")
            seen.add(current)
            current = state_predecessors[current]

    # Correction lineage is a directed representation graph. It must remain acyclic so
    # historical correction cannot rewrite itself back into an earlier representation.
    for start in correction_edges:
        seen = set()
        current = start
        while current in correction_edges:
            if current in seen:
                raise InvariantViolation("Correction lineage must be acyclic.")
            seen.add(current)
            current = correction_edges[current]


def reconstruct_current_state(objects, subject_id):
    """Return the unique authoritative current State for a subject.

    A current state is the unique State in the subject's validated lineage that
    has no successor. This is intentionally deterministic: multiple terminal
    states are rejected rather than guessing which branch is authoritative.
    """
    validate_all(objects)
    states = [obj for obj in objects if isinstance(obj, State) and obj.subject_id == subject_id]
    if not states:
        raise InvariantViolation(f"No State exists for subject {subject_id!r}.")
    by_id = {state.id: state for state in states}
    successors = {}
    for state in states:
        if state.previous_state_id is not None:
            if state.previous_state_id not in by_id:
                raise InvariantViolation("State lineage references a state outside the subject lineage.")
            if state.previous_state_id in successors and successors[state.previous_state_id] != state.id:
                raise InvariantViolation("State lineage has competing current branches.")
            successors[state.previous_state_id] = state.id
    heads = [state for state in states if state.id not in successors]
    if len(heads) != 1:
        raise InvariantViolation("State history must have exactly one authoritative current state.")
    return heads[0]
