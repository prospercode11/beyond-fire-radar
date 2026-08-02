# Phase 7 — Notifications and workflow

Status: complete for the internal/local workflow gate on 2026-08-01.

## Scope

Internal notifications, assignment, acknowledgment, escalation, revocation, status transitions, suppressions, and existing-client import.

## Gate

Duplicate jobs do not duplicate alerts; suppression wins; permissions are enforced; all actions are audited; no consumer outreach is introduced.

## Delivered

- Added migrations `0012_internal_workflow` and `0013_workflow_state_guards` for internal alerts, in-app notification jobs, terminal-safe escalation state, assignment history, append-only notes, and existing-client roster imports/rows.
- Added stable incident-level alert deduplication and repeat-safe notification-job creation. The current alert type is an internal structure-review item; it is not a damage, coverage, claim-validity, probability, or contact conclusion.
- Added explicit eligibility checks for incident state, score hard gates, reviewer suppressions, resolved property evidence, source acquisition mode, and authorization basis. Synthetic fixture, live-poll, and unauthorized sources cannot create operational alerts.
- Added in-app-only dispatch. No email, SMS, phone, webhook, consumer, or external notification provider exists.
- Added authenticated alert actions for acknowledgment, snooze, resolve, suppress, revoke, escalation, and eligibility-checked unsuppress; suppressed alerts cannot be acknowledged, snoozed, or resolved, resolved/revoked alerts cannot reopen, and every action is audited.
- Added current/historical incident assignment, append-only review notes, and UTF-8 CSV existing-client import with size limits, idempotency/content hashes, row validation, raw-row retention, and audit records.
- Kept live Sarasota polling disabled and made no source-approval or legal claim. Internal client-roster files are clearly distinguished from external-source retrievals.

## Verification evidence

- `./scripts/verify.sh` passed with 41 tests, Ruff, mypy, ESLint, and the Next production build passing.
- `PATH="$PWD/.venv/bin:$PATH" pytest -q apps/api/tests/test_workflow.py` passed (6 tests).
- `PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py migrate` passed on the local SQLite database at migration head, including migrations `0012_internal_workflow` and `0013_workflow_state_guards`.
- A fresh isolated database at `/tmp/bfr-phase7-smoke-final2.u8ttCn/data.db` passed `PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py api-smoke`; the stale default database was not used as evidence.
- Authenticated browser inspection exercised the local dashboard read path and Workflow navigation. Empty/no-alert states remained explicit for fixture data; no fake operational alert was presented.
- Docker/Colima is unavailable on this host, so PostgreSQL/PostGIS and Redis integration tests remain blocked external-service checks rather than being reported as passed.

## Acceptance gate result

The Phase 7 internal/local gate passes: repeat generation does not duplicate alerts or in-app jobs; suppression/revocation/resolution wins over dispatch; current score and matched current property evidence are rechecked before unsuppress; authenticated editor permissions guard mutations; audit records cover generation, actions, dispatch, assignment, notes, and client import; no consumer outreach or external notification channel was added. The final independent Luna sign-off found no critical/high/medium/low findings. The external approval gate remains open for real operational alerting because no approved real Sarasota snapshot and no empirical outcome evidence were supplied.

## Boundaries carried forward

Do not add live Sarasota polling, Boca, Broadcastify, GIS/property automation, empirical calibration, learned models, email/SMS/phone delivery, consumer outreach, or final production dashboard deployment in Phase 7.
