# Phase 5 — Advanced scoring foundation

Status: complete for the local/manual prototype gate

## Scope

Feature registry and availability timestamps, source quality, incident validity, material loss, complexity, fit, data sufficiency, ranking, abstention, explanations, registry, evaluation harness, temporal evidence selection, and rollback metadata.

## Concrete checklist

- [x] Add migration-owned scoring-version registry, score-run history, feature contributions/provenance, and human override records.
- [x] Implement separately versioned source quality, incident validity, property-match quality, material-loss evidence, loss complexity, Beyond Adjusting fit, freshness, and data-sufficiency components.
- [x] Implement transparent weighted-geometric provisional ranking with hard gates, negative/contradictory evidence, missing-data penalties, and explicit evidence tiers.
- [x] Keep scores explicitly non-probabilistic and keep synthetic fixture outputs ineligible for operational alerts.
- [x] Add authenticated score, list, rescore, override, scoring-version, and rollback APIs.
- [x] Preserve feature-level source observation IDs, available-at timestamps, transformations/versions, explanations, and current human overrides.
- [x] Add adversarial tests for vehicle/minor/cancelled signals, missing/uncertain property matches, feature explanations, overrides, rescore, and rollback.
- [x] Run the full repository verification contract and fresh migration round-trip through the Phase 5 migrations.
- [x] Complete the designated independent advanced-architecture/Luna review and fix all critical/high findings.
- [x] Update all execution/data/modeling architecture docs and produce the Phase 5 handoff.

## Gate

The Phase 5 local/manual gate passes: independent versioned scoring components produce a provisional non-probability ranking with feature-level provenance, missing/negative/contradictory evidence gates, explicit human-review bands, as-of boundaries, override protection, score history and predecessor rollback, and leakage-controlled contract/evaluation tests. Real outcomes, calibration, PostgreSQL/PostGIS/Redis execution, and production alert authorization remain external gates; no accuracy or calibration claim is made.
