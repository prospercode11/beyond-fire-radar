# Current state

Updated: 2026-07-31 after verification
Scope: Phase 0 and Phase 1 only

## Implemented

- Repository policy in `AGENTS.md`.
- Architecture/product/modeling/compliance/data/testing documents.
- FastAPI API under `apps/api`.
- SQLAlchemy models and migration `0001_foundation`.
- SQLite local mode; PostgreSQL/PostGIS and Redis service definition.
- One-time configured admin bootstrap, password verification, expiring bearer sessions, and server-side role checks.
- Provider registry for a synthetic fixture and a fail-closed Sarasota live provider.
- Immutable raw snapshot/retrieval table primitives and audit events.
- Next.js web shell under `apps/web`.
- Unit/integration/API smoke verification scripts.
- Independent review and Phase 1 handoff in `docs/reviews/phase-01-foundation-review.md` and `docs/handoffs/phase-01-foundation.md`.

## Explicitly not implemented

Dispatch parsing/import, schema drift execution, raw payload ingestion, canonical observations/incidents, deduplication, property/tax-roll/GIS/permit imports, address normalization, candidate generation, scoring, calibration, opportunity workflow, notifications, maps, model lab, or consumer outreach.

## Environment evidence

The host has Docker CLI but its configured Colima daemon is not running, and the Docker Compose plugin is not installed. Therefore the Compose definitions are present but PostgreSQL/PostGIS/Redis integration could not be truthfully claimed as executed in this environment. SQLite migration and application tests are the runnable local path. The API smoke test passed against the running local server, and the Next.js production shell was served on port 3001 because port 3000 was already occupied.

## Next controlled step

Phase 2 should begin only after this handoff is accepted. It should implement authorized snapshot upload/import and parser/schema-drift behavior behind the provider contract, with real approved snapshots or a clearly visible blocked state.
