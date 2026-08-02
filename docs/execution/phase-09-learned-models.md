# Phase 9 — Learned models and learning infrastructure

## Scope

Phase 9 implements the reproducible, inactive-by-default learning foundation over the Phase 8 evaluation contracts. It does not activate a learned scorer and it does not create an empirical accuracy, calibration, damage, coverage, claim-validity, or conversion claim.

The implementation includes:

- Versioned feature and label contracts with explicit missing-value semantics.
- Immutable training-dataset snapshots bound to an evaluation manifest, including per-feature provenance, feature rows, incident-grouped chronological splits, manifest integrity checks, and leakage reports.
- A dependency-light logistic baseline with threshold metrics, precision intervals, reliability-bin/Brier calibration diagnostics, precision-at-K, predictive-entropy uncertainty, selective-prediction coverage/risk intervals, and model cards/training reports.
- A versioned gradient-boosted adapter boundary that remains blocked when an approved dependency and sufficient eligible data are unavailable.
- Model-release registry states, champion/challenger/predecessor lineage, database-guarded champion uniqueness, idempotent promotion/rollback controls, offline replay, drift reporting, and an explicit administrator approval/serving feature flag.
- Rule-based fallback policy and an authenticated Model Lab posture view that never displays learned probabilities while serving is inactive.

Sarasota remains the only dispatch source in scope. Manual snapshot, CSV, JSON, HTML, fixture, and replay workflows remain available. Live Sarasota polling and all Boca/Broadcastify integrations remain disabled.

## Acceptance gate

The Phase 9 gate is not satisfied by mechanics-only fixtures. A learned release may be promoted only when all of the following are true:

- Real approved outcome labels are bound to a reproducible manifest.
- Time-aware incident-grouped train/validation/test splits pass with no group overlap or future leakage.
- A held-out comparison shows improvement over the approved baseline.
- Calibration is valid for the intended use and top-alert precision improves under the documented review threshold.
- Uncertainty/selective-prediction behavior and error analysis are complete.
- An independent modeling review has no unresolved critical/high findings.
- A human administrator explicitly approves deployment and the serving feature flag is enabled.

The current repository does not have sufficient real approved labels or an enabled serving approval. Therefore the current state is intentionally `rule_based_fallback`; mechanics-only training can produce an inactive release for testing, but it cannot become a champion or support an accuracy claim.

## Migration and interfaces

- Migrations `0017_learning_infrastructure` and `0018_learning_control_actions` own feature contracts, label contracts, training snapshots, model releases, replay runs, drift reports, and guarded model control actions.
- Authenticated routes are under `/api/v1/learning`: dataset creation/list/detail, model training/list/detail, replay, promotion, rollback, drift, and policy.
- `enable_learned_model_serving` defaults to `false` and is not enabled by this phase.
- Every creation, replay, promotion, rollback, and drift operation records an audit event and uses an idempotency key where applicable.

## Verification

The focused suite covers chronological/grouped splits, future-feature and label leakage, logistic mechanics, inactive serving, replay idempotency, drift reporting, fallback policy, blocked directional/synthetic manifests, and the disabled promotion gate. The repository verification contract, migration round-trip, API smoke, production build, and authenticated browser posture checks are recorded in the Phase 9 handoff.

## Explicit non-scope

No live polling, source approval invention, Boca/Broadcastify integration, Phase 10 hardening, property/address matching changes, opportunity-scoring changes, automatic outreach, dashboard deployment, or learned-model activation belongs to Phase 9.
