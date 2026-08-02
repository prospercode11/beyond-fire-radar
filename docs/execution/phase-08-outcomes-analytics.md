# Phase 8 — Outcomes and analytics

## Scope

Structured human labels, append-only funnel/outcome events, property-match accuracy, precision at K, alert usefulness, found-first measurement, reviewer agreement, error taxonomy, and a Model Lab readiness baseline. This phase records internal reviewer outcomes only. It does not add a live source, property automation, outreach, or a learned model.

## Implementation

- Added migrations `0014_outcomes_analytics`, `0015_outcome_integrity`, and `0016_outcome_alert_provenance` for append-only outcome labels/events, reproducible evaluation manifests, and analytics metric rows. Property-match labels bind to the reviewed score/match/candidate/decision; alert-usefulness labels bind to an internal alert.
- Added authenticated, role-checked APIs for idempotent manual labels/events, incident outcome inspection, report generation, and manifest replay.
- Label values and error categories are versioned in code; negative labels require an error taxonomy category. Provenance identifies the manual internal entry mode and does not represent a source approval or legal conclusion.
- Reports freeze incident, score-run, label, event, dispatch retrieval, property import, acquisition-mode, authorization, snapshot-hash, filter, and as-of references in a manifest. Metrics persist numerator/denominator/value/status/warning/details rows and never overwrite prior reports. Historical source links and score boundaries are evaluated against the manifest boundary.
- Metrics keep technical accuracy separate from conversion, show small-sample and synthetic-fixture warnings, and return `accuracy_claim_allowed=false`. Property-match accuracy excludes unresolved labels; precision at K uses deterministic current-score ordering and latest review-relevance labels; found-first is a manually recorded event rate; reviewer agreement uses exact pairwise label agreement; error taxonomy reports approved-category counts.
- Model Lab readiness is a blocked contract (`not_trained`) until real labels, incident-grouped/time-aware splits, leakage checks, held-out evaluation, calibration, error analysis, and administrator approval exist. No learned model is trained in Phase 8.
- Added an authenticated Outcomes/Analytics workspace view that displays manifest provenance, dispatch/property source counts, denominators, warnings, and blocked readiness without presenting probability or conversion claims.

## Acceptance gate

Technical accuracy and conversion remain separate; denominators, small-sample warnings, source modes, and claim status are visible; metrics are reproducible from persisted manifests; prior labels/events/reports remain immutable and auditable.

- [x] Structured label taxonomy, manual outcome events, provenance, idempotency, and audit records.
- [x] Funnel, property-match accuracy, precision at K, alert usefulness, found-first, reviewer agreement, and error taxonomy metrics.
- [x] Manifest-bound reproducibility and persisted metric denominators/warnings.
- [x] Model Lab readiness baseline is blocked without sufficient real held-out labels; no learned model is active.
- [x] Focused label/event/report tests, full verification, migration round-trip, API smoke, and web build recorded in the handoff.
- [x] Independent Luna review completed; critical/high findings addressed. Final review: 0 Critical, 0 High; one documentation-freshness Medium finding was corrected before closure.
- [ ] Official Sarasota property-source approval/terms evidence and approved real snapshot remain external gates.
- [ ] PostgreSQL/PostGIS and Redis integration execution remains blocked because Docker/Colima is unavailable in this environment.

## Boundaries

Live Sarasota polling remains disabled. Dispatch records remain limited to the approved manual/file and fixture/replay workflows already in the repository. Boca, Broadcastify, official property automation, address-to-parcel work beyond Phase 4, consumer outreach, and Phase 9 learned-model training are not included.
