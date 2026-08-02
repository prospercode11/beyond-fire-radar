# Phase 8 handoff — Outcomes and analytics

Status: complete for the internal/local analytics gate. Phase 9 has not started.

## Delivered

- Migrations `0014_outcomes_analytics` through `0016_outcome_alert_provenance` add append-only outcome labels/events, reviewed-prediction and alert bindings, dispatch/property source provenance, evaluation manifests, and analytics metric rows.
- Authenticated reviewer APIs record versioned label types/values, approved error categories, manual funnel events, incident outcome history, report generation, and frozen manifest replay. Explicit idempotency keys prevent duplicate label/event records and replay actions are audited.
- Reports separately measure property-match accuracy, precision at K, alert usefulness, found-first rate, reviewer agreement, error taxonomy, funnel counts, and Model Lab readiness. Each metric includes a denominator, persisted value/status, warning, and calculation details.
- Dispatch retrievals and property imports retain acquisition modes, provider IDs, authorization bases, snapshot/content hashes, and source IDs in every manifest. Synthetic evidence produces an explicit non-real-world warning; reports never authorize live polling, claim legal approval, or turn local fixtures into accuracy evidence.
- The web workspace includes an Outcomes/Analytics view with manifest IDs, source modes, warnings, and blocked Model Lab readiness. No probability or conversion claim is displayed.

## Verification

From the repository root:

```text
./scripts/verify.sh
```

Result: PASS — 43 tests, formatting, Ruff lint, mypy, Next lint, and production build. The focused Phase 8 suite is 2 passed after remediation.

```text
PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py migrate
```

Result: PASS — fresh upgrade through `0016_outcome_alert_provenance`; downgrade to `0014_outcomes_analytics`; re-upgrade through `0016_outcome_alert_provenance` in `/tmp/bfr-phase8-integrity-final2.vfduEx`.

```text
DATABASE_URL="sqlite:////tmp/bfr-phase8-final3-smoke.8nCRDi/data.db" \
RAW_SNAPSHOT_DIR="/tmp/bfr-phase8-final3-smoke.8nCRDi/raw" \
BOOTSTRAP_ADMIN_EMAIL=admin@example.com \
BOOTSTRAP_ADMIN_PASSWORD=change-me-in-development \
PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py api-smoke
```

Result: PASS on a fresh isolated SQLite database after migration. The smoke flow continues to use the repository fixture and confirms authentication, provider posture, fixture import, replay, and canonical incident processing; it is not real-world evidence.

Focused Phase 8 behavior: explicit label/event idempotency and audit replay; alert-usefulness binding; negative-label taxonomy validation; future-event rejection; saved manifest IDs, dispatch/property source provenance, and source acquisition modes; metric denominators, synthetic warnings, and blocked Model Lab readiness.

## Independent review

Final Luna reviewer: Banach (`019fc108-b4d0-7d20-807c-ad1d1a2a823d`), read-only. Result: APPROVED technically; Critical 0, High 0, Medium 1, Low 0. The only Medium finding was stale handoff/review wording and was corrected in this closure update. Luna confirmed alert binding, property-source provenance, explicit idempotency, deterministic metric replay, disabled live polling/outreach/learned-model training, and blocked Model Lab readiness.

## External/integration limitations

- No approved real Sarasota outcome dataset or property-source terms evidence is present. Manual labels against fixtures remain directional pipeline tests only.
- PostgreSQL/PostGIS and Redis were not executed because Docker/Colima is unavailable. No live Sarasota polling, Boca, Broadcastify, property automation, outreach, or learned model was added.

## Next controlled phase

Phase 9 is the next planned step only after this handoff is accepted. It must remain blocked from learned-model deployment until sufficient real labels, valid held-out improvement, calibration, error analysis, and administrator approval exist.
