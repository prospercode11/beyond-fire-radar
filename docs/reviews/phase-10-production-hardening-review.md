# Phase 10 independent review — Production hardening

## Review scope

Pasteur/Luna performed an independent read-only review of the Phase 10 implementation, migration chain, backup and retention controls, security configuration, deployment artifacts, tests, execution documents, and browser acceptance evidence. The review preserved the project boundary: Sarasota remains manual/file/fixture/replay only, live polling is disabled, no approval or license is inferred, and no Phase 11, Boca, Broadcastify, learned serving, notification, or outreach work was started.

## Initial findings and remediation

The initial review found no Critical findings and four High findings. All four were remediated and rechecked:

1. `scripts/backup.py` now restores the database and every manifest-listed raw payload into an explicit target raw directory, validates payload hashes, rejects unsafe manifest paths, and requires `--force` before overwriting an existing restore target. The Phase 10 test and final CLI run verify two restored raw payloads.
2. `scripts/retention.py` now uses a committed pending-purge marker, audited start/failure/completion events, and a retryable per-payload transaction for both dispatch and property payloads. A failure-injection test confirms provenance remains intact and a later run completes the tombstone.
3. Property import payloads now have migration-owned `payload_purge_pending_at` and `payload_purged_at` state and are included in the same retention command. Migration `0021_property_retention_and_purge_state` and the final retention dry run cover this path.
4. Execution documents were held at pending wording until the final verification, browser sweep, independent review, remediation, and handoff evidence were recorded. The checklist, current state, source registry, data dictionary, execution record, review, and handoff now describe the actual closure state.

## Final decision

Approved for the local/staging Phase 10 hardening gate.

Final severity counts: Critical 0, High 0. No critical or high-severity finding remains unresolved.

## Medium findings and disposition

- API documentation is gated by `ENABLE_API_DOCS`; production/staging configuration rejects public API docs. Local development may keep docs enabled for the local workflow.
- The dependency audit now includes runtime extras and records all 18 exact advisories in an explicit owner/deadline applicability review list. Release Engineering must review them by 2026-09-01 or before deployment.
- Parser comparison now returns a controlled HTTP 410 when a referenced raw payload is unavailable.
- The web production build now emits security headers and a cross-origin-aware CSP.
- Chunked requests without `Content-Length`, the browser bearer token's current session-storage location, and the initial login API-unavailable message remain documented residual limitations. They are bounded or observable in the exercised application path and are not Critical/High blockers for this local/staging gate.

## Evidence

- `./scripts/verify.sh`: 90 formatted files, Ruff, mypy, 57 Python tests, web ESLint, and Next production build passed.
- Migration head is `0022_raw_purge_pending_state`; a fresh upgrade, downgrade to `0021` and `0020`, and re-upgrade passed.
- API smoke, fixture-only E2E acceptance, focused hardening/failure-injection tests, dependency audit, backup verify/restore, and retention dry run passed.
- Authenticated production standalone browser acceptance showed the three Sarasota fixture incidents, disabled live polling, source-mode labeling, all eight workspace views without failure text, no final desktop overflow, and a visible 3px keyboard focus outline.

## Remaining limitations

Docker/Colima, PostgreSQL/PostGIS, Redis, managed object storage, managed backup restore, SSO/MFA, TLS/domain, external source approvals, and operator-owned staging recovery remain external gates. No production approval is claimed.
