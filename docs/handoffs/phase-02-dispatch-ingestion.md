# Phase 2 handoff — Dispatch ingestion

Status: implementation complete; controlled handoff conditional on external approval evidence
Commit: recorded after final verification
Next phase: Phase 3 — Incident intelligence, not started

## Delivered

- Sarasota County official dispatch provider metadata and source boundary.
- Manual multipart snapshot upload for CSV, HTML, and JSON with size limits, role checks, request IDs, and explicit `authorized_snapshot` attestation for the official provider.
- Versioned Sarasota parser/schema contract with current official HTML table-shape support, duplicate-header handling, source case/event IDs, timestamps, grid/zone, source wording, and original location preservation.
- Immutable content-addressed raw snapshot storage, raw row retention, normalized dispatch observations, opaque raw references, and an authorized raw-payload read endpoint.
- Source-faithful event taxonomy with explicit unknown/abstention behavior; no working-fire inference from generic wording.
- Schema drift, parser failure, row rejection, zero-row anomaly, import error, parser comparison, and provider-health visibility.
- Atomic idempotency-key reservation and content-hash replay behavior. Duplicate replay does not create duplicate raw snapshots, raw rows, or observations.
- Live Sarasota polling interface remains disabled by default and still fails closed. No CAPTCHA/access-control/rate-limit bypass was added.

## Source and evidence boundary

The initial source is the [Sarasota County 911 Dispatch Reporting interface](https://dispatchreporting.scgov.net/Events?strAgencyID=All). A one-time current public HTML response was parsed successfully on 2026-07-31 with 63 rows and no parser issues. This verifies the parser against the current public table shape; it is not written authorization for automated use.

The real approved-snapshot gate remains open because no written approval artifact or approved snapshot was supplied in this workspace. The repository fixtures are synthetic and are not external evidence. Do not enable live polling or begin Phase 3 until that artifact is attached, imported with its approval reference, and the acceptance result is recorded.

## Acceptance evidence

| Gate | Result | Evidence |
| --- | --- | --- |
| Real approved snapshot parses | Open | No written approval artifact supplied; current public page shape check is recorded separately and not substituted. |
| Parser failure visible | Pass | `test_parser_failure_and_zero_row_anomaly_are_visible`; retrieval errors, schema alerts, and provider health endpoints. |
| Duplicate replay creates no duplicates | Pass | `test_snapshot_upload_replay_and_raw_preservation` and `test_concurrent_same_key_returns_one_retrieval`. |
| Zero-row anomaly detected | Pass | Zero-row fixture, persisted `SchemaAlert`, `ImportErrorRecord`, retrieval status, and health state. |
| Contract tests pass | Pass | 14 API/parser/concurrency tests, repository verification, and web build. |
| Live polling disabled | Pass | `ENABLE_LIVE_SARASOTA_DISPATCH_POLLING=false`; provider contract test and `/healthz`. |

## Final verification commands

Run from the repository root with the project virtualenv first on `PATH`:

```bash
PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh
PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py migrate
PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py api
PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py api-smoke
curl --fail --silent http://127.0.0.1:8000/healthz
curl --fail --silent http://127.0.0.1:8000/readyz
```

The final local results were: formatting/lint pass, mypy pass, 14 tests passed, web lint/build passed, API smoke passed, health reported `phase: 2-dispatch-ingestion` and `live_polling_enabled: false`, and readiness reported `ready`.

Fresh SQLite migration verification also passed:

```bash
DATABASE_URL="sqlite:///./data/phase2-migration-test-6.db" .venv/bin/alembic -c apps/api/alembic.ini upgrade head
DATABASE_URL="sqlite:///./data/phase2-migration-test-6.db" .venv/bin/alembic -c apps/api/alembic.ini downgrade base
DATABASE_URL="sqlite:///./data/phase2-migration-test-6.db" .venv/bin/alembic -c apps/api/alembic.ini upgrade head
```

PostgreSQL/PostGIS and Redis integration remains unverified because the configured Docker/Colima daemon and Docker Compose plugin were unavailable.

## Scope lock

This handoff does not include canonical incidents, cross-source deduplication, property resolution, scoring, dashboards, notifications, outreach, Boca radio, or Broadcastify. Phase 3 has not begun.
