# UMVWA — Supabase Connection Gate v1.0
Date: 4 September 2026

## Current state
- Supabase project created by founder: `UMVWA Pilot`
- Region: West Europe — London
- Plan: Free
- Current local runtime baseline: v3.2 pilot runtime
- Local regression: 53/53 PASS
- Warnings-as-errors: 53/53 PASS
- Python compilation: PASS

## Work completed in this gate
- Added PostgreSQL/Supabase dependency support while preserving SQLite for local tests.
- Added a Postgres schema matching the verified v3.2 runtime schema.
- Added compatibility handling for the existing parameterized SQL contract.
- Adapted the existing evidence upsert for PostgreSQL.
- Adapted the communication recipient search for PostgreSQL.
- Preserved existing SQLite test behaviour.
- Added explicit `DATABASE_URL` switch: SQLite remains default; Supabase/Postgres activates when `DATABASE_URL` is present.

## Security boundary
- No Supabase credential, database password, API key, or connection string is stored in the repository.
- The database connection must be supplied through an environment secret.
- Supabase Data API exposure is not relied upon for UMVWA application authorization.
- Explicit database policies remain a required hosted security gate.

## Next founder action
Open the Supabase project's **Connect** panel and retrieve the **Session pooler** connection string (port 5432) for the persistent FastAPI backend. Do not send the full string in chat because it contains the database password. The connection string is stored only as a deployment secret/environment variable.

## Important
This gate does not claim that the hosted database has been migrated or that the hosted application is live. That requires a real authenticated database connection and runtime verification.
