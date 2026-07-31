# Phase 3 — Incident intelligence

Status: complete for the Sarasota manual/fixture prototype boundary
Updated: 2026-07-31

## Scope and guardrails

Phase 3 converts Sarasota dispatch observations already imported through the approved manual/file workflow into canonical incidents. It does not poll Sarasota, add Boca radio or Broadcastify, resolve addresses to parcels, score opportunities, build the final dashboard, contact consumers, or add learned models.

The external-source approval gate remains intact. `ProviderRetrieval.acquisition_mode` distinguishes `manual_snapshot`, `synthetic_fixture`, and future `live_poll` input. Incident processing accepts only the first two modes; live collection remains disabled by `ENABLE_LIVE_SARASOTA_DISPATCH_POLLING=false` and is rejected by the processing service. This is a narrow workflow distinction for already supplied data, not invented legal approval.

## Implemented contract

- `0004_incident_intelligence` through `0006_scope_incident_aliases_by_provider` add canonical incidents, aliases, source-observation links, linkage decisions, evidence, timelines, merge/split audit records, processing runs, acquisition provenance, responder evidence, disposition relationships, assignment uniqueness, review-signal history, and provider-scoped source identity.
- Deterministic linkage uses exact source-record identity, compatible exact event/case identifiers, and conservative exact normalized-address/time evidence.
- The probabilistic baseline combines time, normalized address, house number, street tokens, grid, agency, station, event family, event wording, and shared identifiers. It is explainable and versioned as `incident-linkage.v1`; it is not machine learning and never merges on fuzzy similarity alone.
- Bands are explicit: `>=0.88` automatic match, `0.62–<0.88` possible match/human review and kept separate, `<0.62` no match. Deterministic identifier guards can force non-match for reused/conflicting identifiers.
- Cluster consistency rejects over-wide time spans, incompatible near-simultaneous locations, and reused identifiers. Candidate-level explanations preserve why a row was merged or kept separate.
- Classification is source-faithful and versioned as `incident-classification.v1`. It aggregates source taxonomy families, preserves mixed/conflicting event types as contradictory evidence, and never infers a working fire.
- Incident state values follow the specification: Newly observed, Awaiting corroboration, Property unresolved, Likely structure-related, High-confidence structure-related, Disposition pending, Confirmed meaningful incident, Downgraded, False alarm, Closed, Suppressed. Invalid transitions are rejected and valid manual transitions are audited.
- New observations are processed incrementally. Linkage/classification versions and retrieval-level processing runs are persisted; `POST /api/v1/incidents/{id}/rescore` creates a timeline rescore event and preserves prior evidence.
- Merge and split endpoints preserve raw rows, observation IDs, old assignment history, reasons, actors, timelines, and audit events.

## API surface

- `POST /api/v1/incidents/process/retrievals/{retrieval_id}` — process a manual or fixture retrieval once; replay returns the existing processing run.
- `GET /api/v1/incidents` and `GET /api/v1/incidents/{incident_id}` — list/detail with source rows, acquisition modes, retrieval IDs, decisions, evidence, aliases, and timeline.
- `POST /api/v1/incidents/{incident_id}/rescore` — deterministic incremental rescore hook.
- `PATCH /api/v1/incidents/{incident_id}/state` — audited state-machine transition.
- `POST /api/v1/incidents/{incident_id}/merge` — audited manual merge into the path incident.
- `POST /api/v1/incidents/{incident_id}/split` — audited manual split by source observation IDs.

## Acceptance evidence

- Fresh migration upgrade, downgrade to `0003_widen_idempotency_key`, and re-upgrade to head passed on SQLite.
- Full migration downgrade regression with two providers sharing a source ID passed: `head → 0004 → 0003 → head`, with the second provider preserved as an explicit collision when returning to the pre-provider-scoped schema.
- `20` repository tests passed, including replay, same-retrieval and cross-retrieval concurrent processing, provider-scoped identity, duplicate agency rows, missing event numbers, conflicting event types, reused identifiers, separate same-address fires, malformed records, incremental updates, rescore, state rejection/transition, and manual merge/split.
- Isolated application startup on `127.0.0.1:8001` passed health and `scripts/api_smoke.py`; the smoke test processes and replays the Sarasota-shaped fixture and verifies the canonical incident count does not increase.
- Ruff formatting/checks and mypy passed. The required verification script is run again at handoff.
- PostgreSQL/PostGIS and Redis integration execution remains unavailable because Docker/Colima is not running; this limitation is carried forward rather than claimed as passed.

## Gate

Phase 3 is accepted for the local/manual prototype when adversarial deduplication passes; source rows remain inspectable; merge/split actions are audited; contradictions remain visible; acquisition mode is explicit; and no transitive over-merge is accepted. Phase 4 remains explicitly not started.
