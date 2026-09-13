# UMVWA Privacy & Security Pilot Baseline

## Data boundary
UMVWA stores operational records needed for continuity between Executive and Assistant: people identity, work, decisions, dependencies, communications, meetings, artifacts, voice-note metadata/audio, notifications and history.

## Access
Workspace membership is tenant-scoped. Role and authority are separate from authentication. Consequential actions require explicit human authority. Ask UMVWA is permission-filtered.

## Sensitive fields
Raw contact values and raw communication bodies are not returned in Ask source payloads. Assistant views of another person's profile do not expose contact values.

## Voice
Audio is stored behind an authenticated endpoint. The application does not claim a transcript unless a configured transcription provider actually returns one.

## AI
The default AI runtime is disabled. A production model must be explicitly configured. Any production integration must preserve UMVWA's FACT / SYSTEM STATE / AI INFERENCE / RECOMMENDATION distinction and human control over consequential actions.

## Session security
Sessions expire after 24 hours and can be revoked server-side. Browser tokens are tab-scoped via sessionStorage; a future production deployment should prefer an HttpOnly, Secure, SameSite cookie session with CSRF protection if cookie authentication is adopted.

## Backup
SQLite backups are generated through SQLite's backup mechanism and integrity-checked before being reported successful. Off-site replication, encryption-at-rest, retention schedules, and disaster-recovery drills remain deployment responsibilities.

## Pilot requirements before real sensitive data
- TLS termination
- managed secrets
- encrypted durable storage
- off-site backups
- explicit retention/deletion policy
- incident response owner
- access review
- dependency vulnerability scanning
- real-user acceptance testing
