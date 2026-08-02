# Phase 9 handoff — Learned models and learning infrastructure

Status: implementation complete for the inactive local learning-foundation gate. Phase 10 has not started.

## Scope delivered

- Versioned feature and label contracts with missing-value semantics and audited bootstrap creation.
- Manifest-bound training dataset snapshots with persisted rows, source provenance, per-feature provenance, incident-grouped chronological splits, manifest boundary checks, and leakage reports.
- Dependency-light logistic baseline with threshold precision/recall, Wilson precision intervals, reliability-bin/Brier diagnostics, precision-at-K, predictive entropy, selective-prediction coverage/risk intervals, model cards, and training reports.
- Versioned gradient-boosted adapter boundary that remains blocked when no approved dependency/adapter is available.
- Model release registry with blocked/inactive/candidate/challenger/champion/retired/rolled-back states, feature/label/dataset lineage, predecessor links, model replay, feature drift, rollback, and rule-based fallback.
- Idempotent administrator promotion/rollback control actions, database-guarded single champion, locked control reads, and explicit `enable_learned_model_serving=false` default.
- Authenticated Model Lab posture surface showing fallback, inactive release history, approval boundary, and no learned probability display.

## Source and legal boundary

Sarasota County remains the only dispatch source. Manual Sarasota snapshots, CSV/JSON/HTML files, fixtures, and replay remain available. Live Sarasota polling remains disabled. Real-data eligibility is derived from persisted approved-provider retrievals/imports, recognized manual acquisition mode, explicit manual attestation metadata, source hashes, and manifest consistency; a manifest claim string alone cannot authorize training. No permission or legal approval is invented. Boca, Broadcastify, property-ingestion changes, opportunity-scoring changes, outreach, and Phase 10 hardening were not started.

## Verification evidence

Final closure run on 2026-08-02:

- `./scripts/verify.sh` — PASS: 79 files formatted, Ruff lint, mypy for 44 source files, 47 Python tests, web ESLint, and Next production build.
- `PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py migrate` — PASS: current local database remained at migration `0018_learning_control_actions`.
- Fresh migration round-trip in `/tmp/bfr-phase9-integrity-final.IPf1VK` — PASS: upgraded through `0018_learning_control_actions`, downgraded to `0017_learning_infrastructure`, and re-upgraded through `0018_learning_control_actions`.
- Isolated `api-smoke` in `/tmp/bfr-phase9-smoke-final.yeUWsi` — PASS.
- `PATH="$PWD/.venv/bin:$PATH" pytest -q apps/api/tests/test_learning_infrastructure.py` — PASS: 4 tests.
- `git diff --check` — PASS.
- Authenticated production browser check against the stable local API — PASS: Model Lab showed `Rule Based Fallback`, `Not active`, and probability display off; desktop and 390×844 mobile checks had no console warnings/errors and no final horizontal overflow (`bodyScrollWidth=375`, `innerWidth=390`).

The final repository verification and migration/API checks were rerun after the implementation and documentation closure edits.

Implementation commit: `7ef5f6f` (`Complete Phase 9 learning infrastructure`).

PostgreSQL/PostGIS and Redis were not executed because Docker/Colima is unavailable on this host. This is an explicit environment limitation, not production integration approval.

## Acceptance boundary

The current policy is `rule_based_fallback`. No model is active and no accuracy claim is allowed. Real approved labels, held-out improvement over baseline, valid calibration, improved top-alert precision, complete error analysis, human administrator approval, and the serving feature flag remain closed gates.

## Independent review

Final independent Luna review: Pascal/Nietzsche (`019fc13c-43c6-7f42-bcb0-041ad3073fd5`), read-only. Result: APPROVED for the inactive local Phase 9 gate; Critical 0, High 0, Medium 1 documentation note, Low 0. The note identified stale pending-review wording and missing data-dictionary detail; both are corrected in this closure update. The review confirmed the five remediated High findings are closed and confirmed that learned serving remains disabled.
