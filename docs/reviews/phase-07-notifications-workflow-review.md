# Phase 7 — Independent Luna review

Review date: 2026-08-01
Reviewers: independent Luna agents `019fc0ba-23fd-7ea0-a69f-ef9490bb0ae8` and `019fc0cb-92bc-70f3-9657-b036566f00f9`
Scope: Phase 6 authenticated dashboard integration and Phase 7 internal notifications/workflow changes; read-only reviews of the current worktree.

## Initial review findings

The first independent Luna review found no critical findings and six high-severity findings:

1. Resolved and revoked alerts could be changed again because the alert action guard only blocked suppressed alerts.
2. Unsuppress reopened an alert without rechecking source authorization, client suppression, incident state, score gates, or current property evidence.
3. Notification dispatch marked any pending channel as delivered, so a non-in-app job could violate the internal-only boundary.
4. Alert and notification deduplication could race between the existence check and insert.
5. Escalation was named in the Phase 7 scope but had no model state, endpoint, audit action, or UI control.
6. The Phase 7 independent review artifact referenced by execution documents did not yet exist.

Luna also identified medium-severity improvements: fixture/manual source labeling in the dashboard, missing audit evidence for idempotent client-import replay, incomplete workflow controls in the UI, and missing tests for terminal states, unsupported channels, RBAC, and unsuppress eligibility.

## Remediation

- Terminal `resolved` and `revoked` alerts now reject every further action. Suppressed alerts only permit an eligibility-checked unsuppress operation.
- Unsuppress reloads the incident and score, re-evaluates all alert gates, refreshes the immutable evidence snapshot, and only requeues a previously suppressed in-app job when eligibility still holds.
- `notification_jobs` is database-constrained to `channel = 'in_app'`; dispatch rejects any non-in-app job defensively and never delivers it.
- Alert and job creation use nested transactions and uniqueness constraints to make repeated/concurrent generation return an existing record instead of producing duplicate rows or silently delivering a second job.
- Added the `escalated` state, actor/time fields, authenticated endpoint, audit event, and dashboard action. Escalated alerts can be resolved but cannot reopen after resolution.
- Added migration `0013_workflow_state_guards`, with SQLite batch-alter handling for both fresh databases and databases that already applied `0012_internal_workflow`.
- Added source acquisition modes to incident summaries and safe fixture/manual labels in the dashboard; idempotent client-import replay is now audited.
- Added focused tests for terminal transitions, escalation, unsuppress eligibility, the notification channel constraint, and replay audit coverage.

## Verification evidence

- `./scripts/verify.sh` — PASS, 41 tests, Ruff, mypy, ESLint, and Next production build.
- `PATH="$PWD/.venv/bin:$PATH" pytest -q apps/api/tests/test_workflow.py` — PASS, 6 tests.
- `PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py migrate` — PASS on the existing local SQLite database.
- Fresh SQLite migration through `0013_workflow_state_guards` — PASS at `/tmp/bfr-phase7-migration.t35mYt/data.db` and the final isolated smoke/browser databases.
- Fresh isolated API smoke — PASS at `/tmp/bfr-phase7-smoke-final2.u8ttCn/data.db`.
- Authenticated browser verification — PASS: dashboard sign-in, fixture/manual source distinction, incident detail source mode `synthetic_fixture`, source-preserving workbench, Workflow navigation, explicit zero-alert state, and in-app-only/no-outreach boundary.
- PostgreSQL/PostGIS and Redis integration execution remains unavailable because Docker/Colima is not running; it is documented as blocked rather than passed.

## Follow-up and final sign-off

A follow-up Luna review identified two additional high-severity safety gaps and one medium source-label issue: unsuppress did not verify current score/property state, resolved alerts could still deliver pending jobs, and the Command Center source card hardcoded manual snapshots. Those findings were fixed with current-score/current-property eligibility checks, resolved-job suppression, and acquisition-mode-derived source-card labels. Focused tests, full verification, fresh migration, API smoke, and browser inspection were rerun afterward.

Final independent Luna sign-off was completed by agent `019fc0d5-a42d-7b50-bb5f-4a80a715ba38` against the remediated worktree. Result: Critical none; High none; Medium none; Low none. Recommendation: approved for the Phase 7 internal/local gate. No Phase 8 work is included in this change.

## Residual limitations

No real approved Sarasota snapshot or empirical outcome labels were supplied. Ordinary fixtures correctly remain ineligible for operational alerts. Live Sarasota polling, Boca, Broadcastify, external notification channels, consumer outreach, and production identity/MFA remain disabled or out of scope.
