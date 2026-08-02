# Phase 10 — Production hardening

## Scope

Phase 10 closes the v1 implementation with a controlled deployment and operations foundation. It does not activate a live source, learned serving, owner outreach, or any later source integration.

- threat-model and authorization-boundary controls;
- secure settings, trusted hosts, request/upload/archive limits, rate limiting, session lifecycle, and security headers;
- tamper-evident audit chaining and integrity inspection;
- structured request logs, bounded in-process metrics, health/readiness, provider circuit/queue status, and error-tracking configuration points;
- SQLite backup/restore tooling, PostgreSQL dump/restore commands, object-storage adapter, raw-payload retention tombstones for dispatch and property imports, and a dry-run-first failure-safe retryable purge command;
- production Dockerfiles, Render release/migration configuration, staging/production templates, local one-command startup, rollback guidance, and cost/configuration notes;
- concurrency, latency-budget, failure-injection, migration round-trip, dependency, accessibility, browser, and final E2E acceptance checks;
- final architecture, security, data-integrity, UX, and independent Luna reviews.

## Explicit boundaries

Sarasota dispatch data remains manual/file/fixture/replay only. `ENABLE_LIVE_SARASOTA_DISPATCH_POLLING=false` is required by the checked-in development and deployment templates. Manual acquisition mode is persisted and visible separately from `live_poll`; the external approval gate is unchanged. No legal approval, credential, source license, accuracy, coverage, damage, claim-validity, or conversion claim is inferred.

The local SQLite path is a runnable development path, not a production substitute for PostgreSQL/PostGIS. Redis and S3/R2 are adapters with fail-closed production settings; their live services require deployment-specific credentials and were not available on the implementation host.

## Acceptance gate

The gate passes only when:

1. `./scripts/verify.sh`, migration upgrade, API smoke, migration downgrade/re-upgrade, dependency audit, and relevant E2E/browser checks have current recorded evidence.
2. The security/access review and threat-model review have no unresolved critical or high-severity findings.
3. Backup verification/restore and the raw-payload retention dry-run/apply mechanics are exercised; restore targets are explicit and overwrite requires confirmation.
4. Concurrent rate limiting, upload/archive limits, immutable audit/object-storage checks, failure behavior, and a bounded local latency target are tested.
5. Production configuration rejects insecure bootstrap, SQLite, HTTP, wildcard-host, memory-rate-limit, non-ready Redis, and public API-doc defaults.
6. Manual Sarasota replay is idempotent and does not create duplicate canonical incidents; live polling remains disabled.
7. Known external limitations are documented and no Phase 11/consumer-outreach work has started.

## Evidence recorded for this closure

| Check | Result | Evidence |
| --- | --- | --- |
| Python/web verification | Pass | `./scripts/verify.sh`: 90 formatted files, Ruff, mypy, 57 tests, ESLint, and Next production build |
| Migration contract | Pass | Local head `0022_raw_purge_pending_state`; fresh upgrade/downgrade/re-upgrade round-trip passed |
| API smoke/replay | Pass | `python scripts/dev.py api-smoke` and final fixture E2E replay passed |
| Dependency audit | Pass with reviewed advisories | `scripts/dependency_audit.sh`; explicit applicability/upstream-availability list in `docs/security/dependency-audit.md` |
| Backup/restore | Pass on SQLite; PostgreSQL command path documented | `apps/api/tests/test_phase10_hardening.py`, `docs/operations/backup-restore.md` |
| Security/access | Pass after remediation | `docs/security/phase-10-access-review.md`, `docs/reviews/phase-10-production-hardening-review.md`; no Critical/High findings remain |
| Browser/UX | Pass | Authenticated production standalone build: all eight views, fixture incidents, disabled polling, no failure text, keyboard focus |
| External services | Blocked on host | Docker/Colima unavailable; not represented as a pass |

## Out of scope

Phase 11+ product work, live Sarasota polling, Boca, Broadcastify, automatic property retrieval, new machine learning beyond the inactive Phase 9 baseline, dashboard redesign, public deployment, and consumer outreach.
