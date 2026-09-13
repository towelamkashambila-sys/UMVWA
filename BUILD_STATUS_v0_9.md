# UMVWA Build Room — v0.9

## Boundary
Real-time transport + notification delivery + actor-bound voice-note integrity.

## Implemented
- Workspace/member-scoped notification inbox.
- Recipient-owned read/unread notification state.
- Lifecycle transitions create notifications in the same transaction as state/history/event mutation.
- Server-Sent Events transport for persisted operational events; clients reconnect using the last event timestamp.
- Voice-note author is bound to the authenticated user.
- Removed duplicate voice-note event emission at API layer; canonical creation path emits exactly one event/history record.
- Removed duplicate contacts route decorator.
- Added pytest configuration for deterministic asyncio fixture scope.

## Verification
- 23/23 automated tests PASS under normal execution.
- compileall PASS.
- A warnings-as-errors run exposed ResourceWarning database-connection cleanup issues during TestClient/SSE execution; this remains an engineering gap and is not claimed closed.

## Exit condition
CONSTRUCTION FUNCTIONALLY PASS; WARNINGS CLEANLINESS REMAINS OPEN.
Production readiness is not established: durable production database, storage/audio upload pipeline, real STT provider, push/web/mobile background delivery, observability, deployment, E2E and commercial validation remain open.
