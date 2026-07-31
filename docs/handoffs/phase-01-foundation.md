# Phase 1 handoff — Foundation

Date: 2026-07-31
Phase: 1 of 10
Next phase: Phase 2 — Dispatch ingestion (not started)

## Work completed

- Created repository governance in `AGENTS.md`.
- Created Phase 0 architecture, product, data, modeling, compliance, threat, testing, and execution documents.
- Created later-phase task files for Phases 2–10.
- Created a Python/TypeScript monorepo foundation.
- Added FastAPI, SQLAlchemy, Alembic, session authentication, five roles, administrator-only provider controls, and immutable audit events.
- Added migration-owned foundation tables for users, roles, sessions, audit events, providers, retrievals, raw snapshots, health, import jobs, feature flags, and legal approvals.
- Added provider metadata/registry contracts, a synthetic fixture provider, and a disabled Sarasota live provider.
- Added PostGIS/Redis Docker service definitions and conditional PostGIS extension creation for PostgreSQL migrations.
- Added the Next.js web shell, ESLint configuration, production build, and dependency audit protections.

## Files and areas changed

- `AGENTS.md`, `README.md`, `.env.example`, `pyproject.toml`, `.gitignore`
- `apps/api/app/`
- `apps/api/migrations/`
- `apps/api/tests/`
- `apps/api/fixtures/`
- `apps/web/`
- `infra/docker-compose.yml`
- `scripts/`
- `.github/workflows/ci.yml`
- `docs/`

## Commands run and results

| Command | Result |
| --- | --- |
| `.venv/bin/python -m alembic -c apps/api/alembic.ini upgrade head` | Passed on fresh SQLite database |
| Fresh SQLite `upgrade head`, `downgrade base`, `upgrade head` | Passed |
| `.venv/bin/python -m ruff format --check apps/api scripts` | Passed |
| `.venv/bin/python -m ruff check apps/api scripts` | Passed |
| `.venv/bin/python -m mypy apps/api/app` | Passed, 17 source files |
| `.venv/bin/python -m pytest` | Passed, 8 tests |
| `npm --prefix apps/web run lint` | Passed |
| `npm --prefix apps/web run build` | Passed, static `/` build |
| `npm audit --prefix apps/web --audit-level=high` | Passed, 0 vulnerabilities |
| `.venv/bin/python scripts/api_smoke.py` against running API | Passed |
| Logout/revocation smoke against running API | Passed |
| `GET /healthz`, `GET /readyz`, web `GET /` | Passed |

## Real versus mocked integrations

Real local integrations: SQLite migrations, FastAPI HTTP server, database-backed sessions/audits, provider metadata, and Next.js build/server.
Synthetic/test-only: the dispatch fixture. It is explicitly not an external authority and is not model-accuracy evidence.
Not run: PostgreSQL/PostGIS and Redis containers because Docker’s configured Colima daemon was unavailable; Sarasota live polling because authorization and terms are unconfirmed and the feature flag is false.

## Known limitations and open risks

- External service integration gate is open.
- Production identity/MFA, rate limiting, secret management, TLS, retention, backup/restore, and dependency/security review remain.
- Provider retrieval, parsing, schema-drift detection, retries, replay, and raw payload ingestion begin in Phase 2.
- No incidents, property records, geospatial matching, scores, probabilities, alerts, dashboards, notifications, or outcomes exist yet.
- The web shell is not an operational dashboard.

## Acceptance decision

Phase 0 and Phase 1 local acceptance gates pass. This commit is ready for review and controlled handoff, not for production deployment. Phase 2 must not begin until this document and the independent review are accepted.
