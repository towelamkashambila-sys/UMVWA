# UMVWA Build Status v1.1 — People Operational Profile

## Boundary
People/Contacts are promoted from a directory primitive into an operational identity surface. This does not create a CRM module. The person profile connects identity and contact details to existing shared operational reality: relationships, work, meetings, communications, voice notes, decisions, dependencies, and history.

## Implementation
- Added `person_profile(org, person_id)` in `app/graph.py`.
- Added authenticated `GET /api/people/{org_id}/{person_id}`.
- Preserved workspace isolation.
- Included inverse relationships so relationship context is not one-sided.
- Meeting participation is resolved through canonical `Person -> Meeting` object links.
- Communications remain grounded in sender/recipient participation while ingestion can continue migrating toward link-based participation.

## Verification
- 26/26 tests PASS.
- 26/26 tests PASS with warnings treated as errors.
- `python -m compileall -q app` PASS.
- Existing regression suite remains green.
- Cross-workspace person lookup rejected.

## Exit condition
PASS for this construction boundary.

## Not yet claimed
This is not production-ready People/Contacts. Production still requires stronger authorization policy evaluation, durable database/storage, contact lifecycle/edit semantics, real ingestion integrations, UI, audit hardening, and end-to-end verification.
