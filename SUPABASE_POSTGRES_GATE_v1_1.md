# UMVWA — Supabase PostgreSQL Gate v1.1

## Status

**Prepared — not live-verified yet.**

## Verified locally

- PostgreSQL driver: `psycopg[binary]==3.2.10`
- `DATABASE_URL` runtime switch implemented.
- PostgreSQL-compatible schema present in `supabase_schema.sql`.
- Row Level Security is enabled on all 26 application tables as defense-in-depth; no public/anon/authenticated policies are created by the schema.
- Existing SQLite path remains the default for local/test execution.
- Existing regression suite remains the compatibility baseline.

## Founder-confirmed Supabase configuration

- Project: UMVWA Pilot
- Connection method: Session pooler
- Format: Python
- Port: 5432
- Database: `postgres`
- Host: Supabase AWS-based pooler host (credential not stored here)

## Next live gate

Run `scripts/verify_postgres.py` with `DATABASE_URL` supplied through the deployment environment. The script:

1. initializes the UMVWA schema if needed;
2. verifies the expected public tables;
3. verifies a real SQL round-trip;
4. prints no password or connection string.

## Security boundary

Do not commit `DATABASE_URL`, passwords, API keys, or full connection strings to source control or chat. The application reads the connection from the environment.

## Not yet claimed

- Supabase live connection PASS
- Supabase schema migration PASS
- hosted runtime PASS
- production readiness

## Boundary hardening completed — 4 September 2026

- Local SQLite backup is now explicitly blocked when PostgreSQL is active; the runtime will not pretend a local SQLite file is a PostgreSQL backup.
- The admin backup endpoint returns HTTP 503 with a provider-backup message when PostgreSQL is active.
- Container persistence paths are explicitly mapped to `/data` for SQLite fallback, backups, and voice storage.
- New regression coverage verifies these boundaries.
- New regression coverage verifies RLS hardening and credential absence from the schema.
- SQLite initialization explicitly strips PostgreSQL-only RLS statements so the shared schema remains compatible with the local fallback.

## Latest local regression

- Python compilation: PASS
- Full tests: **57/57 PASS**
- Warnings-as-errors: **57/57 PASS**

## Remaining gate

Live Supabase/PostgreSQL connection and hosted runtime verification remain unexecuted because no database secret or connected deployment environment is available to this session.
