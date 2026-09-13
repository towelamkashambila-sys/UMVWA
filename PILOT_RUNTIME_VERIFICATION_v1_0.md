# UMVWA Pilot Runtime Verification v1.0

## Purpose
Move the internally verified UMVWA build toward a real pilot without overclaiming browser or hosted deployment evidence.

## Verified in this environment
- Application starts under Uvicorn.
- `/api/health` returns `status=ok` and persistence reachable.
- `/api/ready` returns `status=ready` with database integrity OK.
- Landing page serves HTTP 200 and contains UMVWA branding.
- Real HTTP login succeeds for the seeded Executive pilot identity.
- Authenticated session is returned from the server.
- Executive Driver's Seat endpoint is reachable.
- User and workspace personalization endpoints are reachable.
- Workspace endpoint is reachable.
- Temporal work endpoint is reachable.
- History endpoint is reachable.
- Server-side logout revokes the session; subsequent session access is rejected.
- Full automated regression suite passes.

## Boundary discovered and fixed
The Settings UI used a `<select>` for notification preference but read `.checked` as if it were a checkbox. The save path was corrected to read the select's boolean string value. A regression test now locks this contract.

## Not yet verified
- Browser UI E2E in this environment: Playwright is installed, but its navigation is blocked by the execution environment's browser policy (`ERR_BLOCKED_BY_ADMINISTRATOR`). A system Chromium executable is present, but the policy prevents local browser navigation.
- Public hosted deployment: no Cloudflare/Supabase credentials are connected.
- Production persistence: current pilot foundation uses SQLite; a managed database migration is required before public production use.
- Real STT/LLM providers: provider seams exist, but no production credentials are connected.
- Real Executive + EA pilot: not yet run.

## Exit condition for this gate
Do not call the pilot production-ready until hosted deployment, managed persistence, browser/device E2E, real AI/STT, and real-user workflow verification have passed.
