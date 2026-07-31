# Beyond Fire Radar

Beyond Fire Radar is an internal, research-only property-loss intelligence system for Beyond Adjusting. The first release is intentionally conservative: it establishes the governed foundation for authorized source imports, evidence provenance, review workflows, and future scoring without making insurance, coverage, damage, or contact claims.

## Current scope

Phase 0 and Phase 1 are complete in this repository:

- Architecture, product, modeling, compliance, data, testing, execution, and handoff documents.
- FastAPI modular-monolith API with SQLAlchemy and Alembic migrations.
- Local SQLite development mode plus PostgreSQL/PostGIS and Redis Docker definitions.
- Password-based bootstrap authentication with database-backed sessions and role checks.
- Immutable audit events for security-sensitive actions.
- Provider registry and provider health metadata, with Sarasota live polling disabled by default.
- Synthetic fixture metadata for repeatable foundation tests. Fixtures are never accuracy evidence.
- Small Next.js TypeScript shell that reports foundation status.

Dispatch parsing, property imports, geospatial matching, learned scoring, notifications, and outreach are Phase 2+ work and are not implemented here.

## Local setup

Requirements: Python 3.12+ for the supported runtime, Node.js 20+, and npm. Python 3.9 is accepted by the current dependency floor for development compatibility.

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test,quality,postgres]'
python scripts/dev.py migrate
python scripts/dev.py api
```

In another terminal:

```bash
npm --prefix apps/web install
npm --prefix apps/web run dev
```

Open [http://localhost:3000](http://localhost:3000). The API is available at [http://localhost:8000/docs](http://localhost:8000/docs).

The first user can be created once with the configured `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` through `POST /api/v1/auth/bootstrap`. The bootstrap endpoint is closed after the first user exists.

## Verification

Run the required checks from the repository root:

```bash
./scripts/verify.sh
```

Individual commands are available through `python scripts/dev.py --help`. The CI workflow runs formatting checks, linting, type checking, unit/integration tests, the API smoke test, and the web production build.

## PostgreSQL/PostGIS and Redis

The supported service definition is `infra/docker-compose.yml`. If the Docker Compose plugin is available:

```bash
docker compose -f infra/docker-compose.yml up -d
```

Then set `DATABASE_URL=postgresql+psycopg://...` before running migrations. The local SQLite mode keeps the foundation runnable when Docker is unavailable; it does not replace the production PostGIS requirement.

## Governance

Read [AGENTS.md](AGENTS.md) before changing the repository. Start with [docs/execution/current-state.md](docs/execution/current-state.md), and use the phase task files to keep future work gated. No automatic consumer outreach exists or is permitted in the current scope.
