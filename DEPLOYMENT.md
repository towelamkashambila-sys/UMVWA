# UMVWA Deployment Runbook

## Local / pilot
1. Copy `.env.example` to `.env` and set production values.
2. Build with `docker compose build`.
3. Start with `docker compose up -d`.
4. Verify `/api/ready` and `/api/health`.
5. Use a real TLS reverse proxy before exposing the service publicly.

## Production boundary
The application is containerized and keeps database/storage paths configurable. A production operator must provide:
- durable encrypted database/storage
- TLS
- secret management
- off-site backups
- monitoring/log aggregation
- alerting
- backup restore drills
- domain/DNS
- account provisioning and recovery process

The repository deliberately does not contain credentials or pretend that a cloud account has been deployed when no account credentials are available.
