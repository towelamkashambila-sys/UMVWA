# UMVWA Render Deployment Gate v1.0

## Purpose
Deploy the canonical UMVWA FastAPI container on a zero-dollar Render Free Web Service while keeping Supabase PostgreSQL as the durable application database.

## Architecture
- Application: UMVWA FastAPI container
- Hosting: Render Web Service (Free)
- Database: Supabase PostgreSQL (Free project)
- Secret: DATABASE_URL entered directly in Render Environment settings
- Health gate: /api/ready

## Safety boundary
The repository contains no database credentials. DATABASE_URL must be supplied as a runtime secret/environment variable. UMVWA production mode refuses to start without DATABASE_URL.

## Render configuration
`render.yaml` declares a Docker web service, Free plan, production environment, demo seeding disabled, and DATABASE_URL as a required unsynced secret.

## Founder action gate
1. Create/connect the source repository in the user's Git provider.
2. Create a Render Web Service from that repository.
3. Select Free plan.
4. Set DATABASE_URL directly in Render Environment. Never paste the value into chat.
5. Deploy.

## Verification gate
After deployment, verify `/api/ready` reports database ready, then run authenticated smoke tests and regression tests against the hosted service.

## Explicit non-claims
This artifact does not claim that Render is connected, that Supabase is live-connected, or that the service is publicly deployed. Those require the founder's external account actions.
