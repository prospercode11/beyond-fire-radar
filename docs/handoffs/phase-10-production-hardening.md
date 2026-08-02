# Phase 10 handoff — Production hardening

Status: complete for the local/staging hardening and deployment-readiness gate. Stop here; Phase 11 and later product work have not started.

## Scope delivered

- Secure production/staging configuration with trusted hosts, explicit HTTPS origins, fail-closed Redis rate limiting/readiness, bounded requests/uploads/archives, session expiry/idle/replacement controls, security headers, structured logs, metrics, and health/readiness endpoints.
- Tamper-evident audit chaining with sequence, predecessor hash, event hash, chain-head verification, and authenticated administrator inspection.
- SQLite backup/verify/restore bundles with manifest-listed raw payloads, hash verification, safe path validation, explicit raw restore targets, and overwrite confirmation; PostgreSQL dump/restore guidance; and an immutable S3/R2 adapter.
- Dry-run-first, audited, failure-safe retention for dispatch and property raw payloads. Purge attempts are pending and retryable before provenance is tombstoned.
- Production API/web images, standalone Next output, Render migration configuration, environment templates, deployment/runbook/rollback/access-review/security/compliance documents, and dependency-audit policy.

## Source and legal boundary

Sarasota County remains the only dispatch source in scope. Manual snapshots and file/fixture/replay workflows remain available. `ENABLE_LIVE_SARASOTA_DISPATCH_POLLING=false`; live polling was not enabled or exercised. The application distinguishes manual, file, fixture, and live acquisition modes and rejects live processing while the live gate is disabled. No permission, legal approval, source license, accuracy, damage, coverage, claim-validity, or outreach conclusion is invented. Boca, Broadcastify, automatic property retrieval, learned serving, external notification, and consumer outreach remain disabled.

## Verification evidence

All final commands were run from the repository root on 2026-08-02:

| Check | Result |
| --- | --- |
| `./scripts/verify.sh` | PASS — 90 files formatted; Ruff, mypy, 57 Python tests, web ESLint, and Next production build passed |
| `PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py migrate` | PASS — local schema already at `0022_raw_purge_pending_state` |
| Fresh Alembic upgrade/downgrade/re-upgrade | PASS — `/tmp/bfr-phase10-migration-rerun2.DxRH1C`; upgraded through `0022`, downgraded through `0020`, re-upgraded through `0022` |
| `python scripts/dev.py api-smoke` | PASS — API at `http://127.0.0.1:8023` |
| `scripts/e2e_acceptance.py` | PASS — fixture mechanics, provenance, replay, review, workflow, outcomes, analytics, RBAC, and alert gate |
| `./scripts/dependency_audit.sh` | PASS — 18 exact advisories reviewed with Release Engineering owner and 2026-09-01/before-deploy deadline; no unreviewed finding |
| Focused hardening tests | PASS — backup/restore, raw restore, retention failure/retry, tamper, limits, concurrency, configuration, and latency checks |
| Backup CLI | PASS — create, verify, and restore; `/tmp/bfr-phase10-backup-final.9Ybd9c`, two raw payloads restored and hash-checked |
| Retention dry run | PASS — candidate 0, purged 0, missing 0, failed 0, property candidates 0 |

The dependency audit emitted the host's known urllib3/LibreSSL warning; this is documented as an environment warning. The reviewed advisory list remains an explicit pre-deployment owner action.

## Browser acceptance

The production Next standalone server was exercised at `http://127.0.0.1:3021` against the authenticated API at port 8023. The final desktop viewport was 1280×720 with no horizontal overflow. The three Sarasota fixture incidents were visible; the UI showed `Sarasota · test fixture` and `Live polling Disabled`. All eight workspace views loaded without `Failed to fetch` or `API unavailable` text. Keyboard navigation produced a visible solid 3px focus outline. Earlier Phase 10 browser checks also covered invalid credentials and API-unavailable/recovery states. The existing Phase 6 390×844 mobile baseline remains the responsive evidence; the Phase 10 browser wrapper did not expose a reliable viewport override, so no new mobile dimension claim is made here.

## Independent Luna review

Pasteur/Luna completed an independent read-only review. Initial result: Critical 0, High 4, Medium 5. The four High findings were fixed: raw-payload restore completeness, failure-safe retention ordering, property payload retention, and premature closure wording. Final result: Critical 0, High 0. Medium dispositions and residual limitations are recorded in `docs/reviews/phase-10-production-hardening-review.md`.

## External limitations and next owner action

Docker/Colima was unavailable, so PostgreSQL/PostGIS, Redis, managed object storage, and managed backup restore were not executed. Production SSO/MFA, TLS/domain, written source approvals, deployment credentials, RPO/RTO, operator-owned staging recovery, and dependency remediation remain external gates. The next action is environment provisioning and approval review, not a new product phase.

Implementation commit: pending the closure commit sequence.
