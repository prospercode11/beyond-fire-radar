# Phase 3 handoff — Incident intelligence

Status: complete for the Sarasota manual/file prototype boundary
Date: 2026-07-31
Next phase: Phase 4 — Property resolution (not started)

## Delivered

- Canonical incident creation from existing Sarasota dispatch observations.
- Deterministic deduplication for exact source identity, compatible agency event/case identifiers, and conservative normalized-address/time evidence.
- Explainable probabilistic linkage baseline `incident-linkage.v1` with match (`>=0.88`), human-review (`0.62–<0.88`), and no-match (`<0.62`) bands.
- Anti-transitive-overmerge cluster limits for time span, location conflicts, and identifier reuse.
- Versioned source-faithful incident classification `incident-classification.v1`, confidence bands, contradiction evidence, classification timelines, and review-signal revocation history.
- Incident timeline and state machine with audited manual transitions.
- Incremental retrieval processing, unique replay runs, and an explicit rescore hook.
- Immutable raw/source observation provenance, acquisition-mode labeling, responder evidence tables, and a reserved disposition relationship.
- Audited manual merge/split controls with source-row preservation and explanations for merged and kept-separate records.
- Manual/fixture-only incident processing gate. Live Sarasota polling remains disabled; no approval or permission was invented.
- Independent Luna review completed; all critical/high findings resolved.

## Files and migrations

- Backend models: [`apps/api/app/models.py`](/Users/shalev/Documents/Beyond%20Claim%20Finder/apps/api/app/models.py)
- Linkage baseline: [`apps/api/app/incidents/linkage.py`](/Users/shalev/Documents/Beyond%20Claim%20Finder/apps/api/app/incidents/linkage.py)
- Incident service: [`apps/api/app/incidents/service.py`](/Users/shalev/Documents/Beyond%20Claim%20Finder/apps/api/app/incidents/service.py)
- API routes/schemas: [`apps/api/app/api/routes/incidents.py`](/Users/shalev/Documents/Beyond%20Claim%20Finder/apps/api/app/api/routes/incidents.py), [`apps/api/app/schemas.py`](/Users/shalev/Documents/Beyond%20Claim%20Finder/apps/api/app/schemas.py)
- Migrations: `0004_incident_intelligence`, `0005_incident_integrity_controls`, `0006_scope_incident_aliases_by_provider`
- Tests: [`apps/api/tests/test_incident_intelligence.py`](/Users/shalev/Documents/Beyond%20Claim%20Finder/apps/api/tests/test_incident_intelligence.py)
- Verification/smoke: [`scripts/verify.sh`](/Users/shalev/Documents/Beyond%20Claim%20Finder/scripts/verify.sh), [`scripts/api_smoke.py`](/Users/shalev/Documents/Beyond%20Claim%20Finder/scripts/api_smoke.py)
- Execution/docs: Phase 3 execution, current state, master checklist, source registry, data dictionary, review, and this handoff.

## Commands and results

- `./scripts/verify.sh` — passed: Ruff format/check, mypy, 20 pytest tests, web lint, and Next.js production build.
- `./.venv/bin/python scripts/dev.py migrate` — passed to head.
- Fresh migration round-trip through `0006_scope_incident_aliases_by_provider` — passed.
- Upgrade from a deliberately duplicated valid `0004_incident_intelligence` state through `0006` — passed; duplicate current assignments and source-record aliases were reconciled without dropping source evidence, and aliases were provider-scoped.
- Full migration downgrade chain `head → 0004 → 0003` and re-upgrade — passed with two providers sharing a source ID; downgrade preserves one source ID and one explicit collision and restores the expected prior-revision indexes.
- `API_BASE_URL=http://127.0.0.1:8001 ... ./.venv/bin/python scripts/api_smoke.py` — passed in an isolated migrated SQLite application; live polling reported false and replay did not increase canonical incident count.
- Full Phase 3 tests — passed: same-retrieval and cross-retrieval concurrent processing, provider-scoped identity, duplicate agency rows, missing event numbers, conflicting event types, reused identifiers, separate same-address fires, malformed records, Sarasota replay, incremental/rescore, state rejection/transition, merge, and split.

## Operating boundaries and limitations

- Use Sarasota manual snapshots/file imports already supplied through the approved workflow, plus deterministic fixtures/replay. Do not enable live polling.
- `manual_snapshot` and `synthetic_fixture` are processable acquisition modes. Future `live_poll` or missing/unknown modes are rejected.
- No PostgreSQL/PostGIS or Redis run was claimed because Docker/Colima was unavailable.
- No property ingestion, address-to-parcel matching, opportunity scoring, final dashboard, consumer outreach, Boca, Broadcastify, or learned model work was started.

## Recommended next controlled action

Review and accept this handoff, then separately resolve the external-source and PostgreSQL/PostGIS/Redis integration evidence before beginning Phase 4. Keep the live Sarasota feature flag false.
