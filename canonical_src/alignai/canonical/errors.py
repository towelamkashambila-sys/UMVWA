class CanonicalModelError(ValueError):
    """Base error for invalid canonical representations."""

class InvariantViolation(CanonicalModelError):
    """A constitutional/data-model invariant was violated."""

class LifecycleViolation(CanonicalModelError):
    """A lifecycle transition is not permitted."""

class RelationshipViolation(CanonicalModelError):
    """A relationship is not permitted by the canonical matrix."""
