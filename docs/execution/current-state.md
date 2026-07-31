# Current state

Updated: 2026-07-31 after Phase 2 verification
Scope: Phase 0 through Phase 2 only

## Implemented

- Repository policy in `AGENTS.md`.
- Architecture/product/modeling/compliance/data/testing documents.
- FastAPI API under `apps/api`.
- SQLAlchemy models and migration `0001_foundation`.
- SQLite local mode; PostgreSQL/PostGIS and Redis service definition.
- One-time configured admin bootstrap, password verification, expiring bearer sessions, and server-side role checks.
- Provider registry for a synthetic fixture and a fail-closed Sarasota live provider.
- Authorized manual Sarasota dispatch snapshot ingestion for CSV, HTML, and JSON.
- Immutable content-addressed raw snapshot storage, raw dispatch rows, normalized observations, and audit events.
- Versioned parser/schema metadata, source-faithful taxonomy, parser comparison, schema alerts, import errors, replay protection, and provider health.
- Next.js web shell under `apps/web`.
- Unit/integration/API smoke verification scripts.
- Independent reviews and handoffs in `docs/reviews/phase-01-foundation-review.md`, `docs/reviews/phase-02-dispatch-ingestion-review.md`, `docs/handoffs/phase-01-foundation.md`, and `docs/handoffs/phase-02-dispatch-ingestion.md`.

## Explicitly not implemented

Live Sarasota polling, canonical incident assembly, cross-source deduplication, property/tax-roll/GIS/permit imports, address normalization, candidate generation, scoring, calibration, opportunity workflow, notifications, maps, model lab, and consumer outreach.

## Environment evidence

The host has Docker CLI but its configured Colima daemon is not running, and the Docker Compose plugin is not installed. Therefore the Compose definitions are present but PostgreSQL/PostGIS/Redis integration could not be truthfully claimed as executed in this environment. SQLite migration and application tests are the runnable local path. The parser also accepted a one-time current HTML response from the official Sarasota dispatch page for shape verification; that is not an authorization claim or an activated polling integration.

The real approved-snapshot gate is intentionally open: no written approval artifact or approved snapshot was supplied in this workspace. Deterministic fixtures and the current public page shape pass parser verification, but they are not substituted for that approval evidence.

## Next controlled step

Phase 3 remains gated. Before it begins, attach and review an approved Sarasota snapshot, run the external-source acceptance check, and execute the available PostgreSQL/PostGIS/Redis integration environment.
