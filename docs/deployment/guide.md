# Deployment guide

## Local

After installing Python and Node dependencies and copying `.env.example` to `.env`, run:

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py local
```

This runs migrations, the API on `API_HOST:API_PORT` (default `127.0.0.1:8000`), and the Next.js development server on port 3000. The first local login uses the configured development bootstrap credentials. The checked-in example keeps live Sarasota polling disabled; the local operator activation requires both polling flags plus `SARASOTA_LIVE_AUTHORIZATION_BASIS=explicit_user_permission` and runs exactly every 900 seconds.

## Staging and production

`render.yaml` defines separate API and web Docker services. It does not provision a database, Redis, or object storage account. The deployment owner must create isolated staging and production PostgreSQL/PostGIS databases, Redis instances, and Cloudflare R2/S3-compatible buckets, then provide secrets through the deployment platform. Use `.env.staging.example` and `.env.production.example` as templates, never as credential files.

The API image installs the PostgreSQL, Redis, and S3 adapters, runs as a non-root user, and exposes `/readyz`. Render runs `alembic upgrade head` as the release command before the API becomes healthy. The web image uses Next standalone output and runs as a non-root user. Set `NEXT_PUBLIC_API_BASE_URL` to the API origin for each environment.

Required production posture:

- `APP_ENV=production`, `ENABLE_BOOTSTRAP=false`, `ENABLE_API_DOCS=false`;
- PostgreSQL/PostGIS `DATABASE_URL`, Redis `REDIS_URL`, `RATE_LIMIT_BACKEND=redis`, and `REDIS_REQUIRED_FOR_READINESS=true`;
- HTTPS `WEB_ORIGIN` and explicit `ALLOWED_HOSTS`;
- S3/R2 bucket, endpoint, region, access key, secret, and separate environment prefix;
- `ENABLE_LIVE_SARASOTA_DISPATCH_POLLING=false`, `ENABLE_SARASOTA_POLLING_WORKER=false`, and `ENABLE_LEARNED_MODEL_SERVING=false` by default; any staging/production polling activation also requires a persisted approved `LegalApproval` and must not use the local explicit-permission basis;
- provisioned administrator through an approved identity/provisioning procedure, not an invented bootstrap path.

## Domain, TLS, cost, and rollback

Terminate TLS at the managed platform or an approved reverse proxy, point the web domain to the web service, and allow the API hostname only from the configured web origin. Confirm certificate renewal and HSTS behavior before production traffic. Select the smallest managed Postgres/PostGIS, Redis, web, API, and R2 storage plans that meet measured load; this repository does not invent a provider quote or spend commitment. Review service usage and storage retention monthly.

For rollback, stop new ingestion, preserve the current deployment and database backup, deploy the previous immutable image, and only run a down migration if a tested rollback plan for that exact release exists. Prefer forward-compatible migrations and an application rollback over destructive schema rollback. Restore into an isolated database first, verify audit-chain integrity and raw references, then switch the service connection.
