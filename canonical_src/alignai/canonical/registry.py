from .models import *

CANONICAL_TYPES={cls.__name__:cls for cls in [Organization,Person,Role,IntendedOutcome,SuccessCondition,OperationalThread,Responsibility,WorkItem,Commitment,Obligation,Dependency,Relationship,Event,Evidence,Claim,TruthResolution,State,Change,Consequence,SignificanceAssessment,Risk,Intervention,Recommendation,Decision,Permission,AuthorityGrant,Delegation,Authorization,Action,ObservedResponse,Validation,Recovery,Notification,Meeting,Artifact,HistoryRecord,Correction,Supersession,ProcessingTrace,ExecutionProofRecord]}
CANONICAL_OBJECT_COUNT=40
