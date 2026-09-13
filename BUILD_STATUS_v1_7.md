# UMVWA Build Status v1.7 — Identity & Workspace Runtime Closure

## Scope
Closed the authenticated identity/workspace boundary exposed by the v1.3-v1.6 UI and voice runtime.

## Implemented
- Added authenticated `GET /api/auth/session` as the authoritative browser identity/session endpoint.
- Removed frontend identity inference from notification data.
- Frontend now derives organization from the authenticated session rather than assuming `org_demo` for workspace reads.
- Voice upload now accepts an explicit workspace id and enforces authenticated membership before writing audio.
- Mutation helper now converts workspace-membership failures into explicit HTTP 403 responses.
- Frontend voice upload supplies the active authenticated workspace.
- Existing approved visual assets remain unchanged.

## Verification
- `PYTHONWARNINGS=error pytest -q`: 36 passed.
- `python -m compileall -q .`: PASS.
- New v1.7 tests cover authoritative session identity and workspace-bound voice upload.

## Exit condition
Authenticated browser identity no longer depends on notification existence, and voice storage cannot be written into an arbitrary workspace through the request parameter.

## Not yet production-complete
Production database, cloud object storage, real STT provider, external integrations, durable deployment, backups/recovery, observability, full E2E/browser automation, and real-user/commercial validation remain open construction boundaries.
