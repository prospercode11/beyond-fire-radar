# Current state

Updated: 2026-07-31 after Phase 3 verification
Scope: Phase 0 through Phase 3 only

## Implemented

- Repository policy in `AGENTS.md`.
- Architecture/product/modeling/compliance/data/testing documents.
- FastAPI API under `apps/api`.
- SQLAlchemy models and migration-owned schema through `0006_scope_incident_aliases_by_provider`.
- SQLite local mode; PostgreSQL/PostGIS and Redis service definition.
- One-time configured admin bootstrap, password verification, expiring bearer sessions, and server-side role checks.
- Provider registry for a synthetic fixture and a fail-closed Sarasota live provider.
- Authorized manual Sarasota dispatch snapshot ingestion for CSV, HTML, and JSON.
- Immutable content-addressed raw snapshot storage, raw dispatch rows, normalized observations, and audit events.
- Versioned parser/schema metadata, source-faithful taxonomy, parser comparison, schema alerts, import errors, replay protection, and provider health.
- Next.js web shell under `apps/web`.
- Unit/integration/API smoke verification scripts.
- Canonical Sarasota incident assembly with deterministic identifiers, conservative explainable probabilistic linkage, confidence/review bands, and anti-transitive-overmerge checks.
- Versioned incident classification, incident timelines, guarded incident state transitions, incremental processing, and explicit rescore hooks.
- Contradictory-evidence preservation, immutable raw/source-row relationships, provenance-bearing incident detail, and explanations for matches and kept-separate candidates.
- Audited manual incident merge and split controls with source-row preservation.
- Phase 3 migrations `0004_incident_intelligence` through `0006_scope_incident_aliases_by_provider`, API routes, adversarial tests, replay verification, independent review, and handoff.
- Independent reviews and handoffs in `docs/reviews/phase-01-foundation-review.md`, `docs/reviews/phase-02-dispatch-ingestion-review.md`, `docs/handoffs/phase-01-foundation.md`, `docs/handoffs/phase-02-dispatch-ingestion.md`, and the Phase 3 review/handoff produced for this commit.

## Explicitly not implemented

Live Sarasota polling, cross-source deduplication, property/tax-roll/GIS/permit imports, address-to-parcel matching, candidate generation, opportunity scoring, calibration, opportunity workflow, notifications, maps, dashboard work, model lab, and consumer outreach.

## Environment evidence

The host has Docker CLI but its configured Colima daemon is not running, and the Docker Compose plugin is not installed. Therefore the Compose definitions are present but PostgreSQL/PostGIS/Redis integration could not be truthfully claimed as executed in this environment. SQLite migration and application tests are the runnable local path. The parser also accepted a one-time current HTML response from the official Sarasota dispatch page for shape verification; that is not an authorization claim or an activated polling integration.

The external-source approval gate remains intact. Phase 3 processing accepts only retrievals explicitly labeled `manual_snapshot` or `synthetic_fixture`; it does not authorize, enable, or process live polling. The upload attestation and provider limitations remain visible, no legal approval is invented, and source acquisition mode is returned in retrieval, processing, and incident detail responses. PostgreSQL/PostGIS and Redis execution remains unavailable on this host.

## Next controlled step

Phase 4 — property resolution — is the next controlled step. It must not begin in this commit. Before that phase, review the Phase 3 handoff, resolve the separately tracked external approval/integration evidence, and keep live Sarasota polling disabled.
