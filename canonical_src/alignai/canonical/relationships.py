from .enums import RelationshipType
from .errors import RelationshipViolation

# Object-type constraints for directed relationship edges. Unlisted combinations are rejected.
ALLOWED_RELATIONSHIPS={
    ("Person","WorkItem"):{RelationshipType.OWNS},
    ("Person","Responsibility"):{RelationshipType.OWNS},
    ("Person","Decision"):{RelationshipType.APPROVES},
    ("Person","Person"):{RelationshipType.DELEGATES},
    ("WorkItem","WorkItem"):{RelationshipType.DEPENDS_ON,RelationshipType.BLOCKS,RelationshipType.ENABLES},
    ("WorkItem","Commitment"):{RelationshipType.REQUIRES},
    ("WorkItem","Obligation"):{RelationshipType.REQUIRES},
    ("Decision","Decision"):{RelationshipType.REPLACES,RelationshipType.SUCCEEDS,RelationshipType.CONFLICTS_WITH},
    ("Claim","Claim"):{RelationshipType.CONFLICTS_WITH,RelationshipType.SUCCEEDS},
    ("Evidence","Claim"):{RelationshipType.ENABLES},
    ("Recommendation","Intervention"):{RelationshipType.ENABLES},
}

def relationship_allowed(source_type,target_type,relationship_type):
    return relationship_type in ALLOWED_RELATIONSHIPS.get((source_type,target_type),set())

def assert_relationship(source_type,target_type,relationship_type):
    if not relationship_allowed(source_type,target_type,relationship_type): raise RelationshipViolation(f"{relationship_type.value} is not allowed from {source_type} to {target_type}.")
