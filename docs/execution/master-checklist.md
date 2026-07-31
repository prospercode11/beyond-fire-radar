# Master checklist

## Phase 0 — Repository audit and architecture

- [x] Repository inventory performed.
- [x] Product specification.
- [x] Architecture decision record.
- [x] System context and data flow.
- [x] Threat model.
- [x] Data model and dictionary.
- [x] Modeling specification.
- [x] Compliance boundaries.
- [x] Source registry.
- [x] Evaluation plan.
- [x] Later-phase task files.
- [x] Phase 0 acceptance gate documented.

## Phase 1 — Foundation

- [x] Monorepo layout.
- [x] Docker Compose definitions for PostgreSQL/PostGIS and Redis.
- [x] Database models and Alembic migration.
- [x] Session authentication and roles.
- [x] Audit framework.
- [x] Provider contract/registry and disabled live provider.
- [x] Synthetic fixture and fixture validation test.
- [x] CI and local verification commands.
- [x] Application/web shell runnable.
- [ ] External PostgreSQL/PostGIS/Redis integration test: blocked by unavailable Docker daemon in this environment.
- [ ] Production identity/MFA and complete user administration: later hardening.
- [x] Phase 1 reviewer findings addressed or documented.
- [x] Phase 1 acceptance gate recorded in handoff.

## Phase 2 — Dispatch ingestion

- [x] Sarasota provider remains fail-closed for live polling.
- [x] Authorized manual snapshot upload boundary with size and attestation checks.
- [x] CSV, HTML, and JSON parser contract with versioned schema metadata.
- [x] Immutable raw snapshot storage and raw-row preservation.
- [x] Source-faithful event taxonomy with explicit unknown/abstain behavior.
- [x] Schema-drift, parser-failure, and zero-row anomaly visibility.
- [x] Provider health, failure state, and schema-alert counters.
- [x] Idempotent replay with no duplicate raw or normalized records.
- [x] Parser comparison and retrieval inspection endpoints.
- [x] Phase 2 contract, migration, API, and replay tests.
- [x] Independent Luna review completed; critical/high findings addressed.
- [ ] Real approved Sarasota snapshot artifact supplied and accepted for the external-source gate.
- [ ] PostgreSQL/PostGIS and Redis integration execution: Docker/Colima unavailable in this environment.
- [x] Phase 2 handoff and acceptance evidence recorded.

## Phase gate rule

Phase 3 must not start until the Phase 2 handoff is accepted, an approved Sarasota snapshot has passed the external-source gate, and the Phase 2 persistence/integration evidence is reviewed. Phase 3 is not started in this commit.
