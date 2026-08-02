# Beyond Fire Radar

Beyond Fire Radar is an internal, research-only property-loss intelligence system for Beyond Adjusting. The first release is intentionally conservative: it establishes the governed foundation for authorized source imports, evidence provenance, review workflows, and future scoring without making insurance, coverage, damage, or contact claims.

## Current scope

Phase 0 through Phase 9 — Sarasota incident intelligence, property resolution, transparent scoring foundation, internal workflow, outcomes/analytics, and inactive learned-model infrastructure — are complete in this repository:

- Architecture, product, modeling, compliance, data, testing, execution, and handoff documents.
- FastAPI modular-monolith API with SQLAlchemy and Alembic migrations.
- Local SQLite development mode plus PostgreSQL/PostGIS and Redis Docker definitions.
- Password-based bootstrap authentication with database-backed sessions and role checks.
- Immutable audit events for security-sensitive actions.
- Provider registry and provider health metadata, with Sarasota live polling disabled by default.
- Synthetic fixture metadata for repeatable foundation tests. Fixtures are never accuracy evidence.
- Authorized manual CSV/HTML/JSON snapshot ingestion for the Sarasota dispatch source, with immutable raw preservation, versioned parsing, taxonomy, schema alerts, replay protection, and retrieval health.
- Canonical Sarasota incidents with conservative deterministic/probabilistic linkage, source-row provenance, contradiction evidence, versioned classification, timelines, state transitions, rescore hooks, and audited merge/split controls.
- Responsive Next.js TypeScript dashboard with Command Center, Incident Stream, Opportunities, Data Health, Settings, review queue, source posture, incident-map empty state, evidence workbench, property context, and explicit loading/error/empty states.
- Authenticated internal alerts, assignments, append-only notes, in-app-only notification controls, and existing-client reference import with suppression safeguards.
- Append-only reviewer outcome labels/events, source-provenance-bound evaluation manifests, directional metrics with denominators/warnings, and a blocked Model Lab readiness view. Reports do not make accuracy, calibration, damage, coverage, claim-validity, legal-approval, or conversion claims.

Phase 4 provides a manual/file prototype for Sarasota property imports and explainable address-to-parcel resolution. Phase 5 adds a versioned, explainable, non-probability opportunity-ranking foundation with feature provenance, hard gates, abstention, review bands, as-of scoring, overrides, rescore history, and rollback through authenticated APIs. Phase 6 adds an authenticated internal dashboard foundation; Phase 7 adds internal-only workflow; Phase 8 adds manual outcome capture and reproducible directional analytics; Phase 9 adds versioned learning contracts, manifest-bound datasets, leakage checks, inactive baseline training, replay, drift, rollback, and explicit approval/serving gates. Official property-source approval, live polling, learned model activation, production dashboard deployment, Boca/Broadcastify, and outreach remain gated; repository fixtures are not real-world accuracy evidence.

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

## Sarasota manual import and Phase 3 incident processing

Live Sarasota polling is intentionally disabled. An authorized internal user can import a manually obtained snapshot with `POST /api/v1/providers/sarasota.official_dispatch/snapshots`, using multipart field `file`, form field `authorized_snapshot=true`, and a unique `Idempotency-Key` header. The repository fixtures under `apps/api/fixtures/` are deterministic test inputs only; they are not external-source evidence.

After import, process a manual or fixture retrieval with `POST /api/v1/incidents/process/retrievals/{retrieval_id}`. Retrieval and incident responses expose `manual_snapshot` or `synthetic_fixture` acquisition mode. The external-source approval gate remains in force; live-collected input is not enabled or processed.

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
