# Independent Luna review — Phase 2 dispatch ingestion

Review date: 2026-07-31
Reviewer: separate GPT-5.6 Luna review agent
Scope: Phase 2 requirements, working-tree diff, migrations, provider/parser/storage/API behavior, tests, documentation, and scope control. The reviewer did not write implementation files or create the commit.

## Findings and disposition

### Critical — external approved-snapshot gate remains open

The repository does not contain a written approval artifact or a real approved Sarasota snapshot. The deterministic fixtures and one-time current public-page parser check cannot be represented as that approval evidence. This is an external evidence blocker, not something the implementation can manufacture. The status is recorded in `docs/execution/current-state.md`, `docs/execution/master-checklist.md`, and `docs/execution/phase-02-dispatch-ingestion.md`.

Disposition: remains explicitly blocked. Phase 3 must not start until the approved artifact is supplied, imported, and reproducibly verified.

### High — concurrent idempotency race

The original pre-check-only path could allow concurrent requests to race and surface a database integrity error. The implementation now reserves the provider-scoped idempotency key with a unique database insert in the same transaction as the retrieval. A unique-conflict recovery path returns the completed job or a deterministic conflict for a different payload. `apps/api/tests/test_dispatch_ingestion.py` includes a two-thread same-key test proving one job, one raw snapshot, three raw rows, and three observations.

The follow-up review also identified the equivalent race when concurrent requests use different idempotency keys for identical bytes. The unique `RawSnapshot.content_hash` conflict is now recovered into the existing retrieval, with a deterministic cross-provider conflict and test coverage in the same concurrency test.

Disposition: fixed and verified. The final Luna confirmation found no remaining critical or high implementation findings.

### High — required Phase 2 review/handoff artifacts missing at review start

The execution checklist and current-state document referenced Phase 2 review and handoff paths before those files existed.

Disposition: fixed by this review document and `docs/handoffs/phase-02-dispatch-ingestion.md`; checklist/documentation references now resolve.

### Medium — upload attestation is not a substitute for written approval

The manual upload route records an explicit `authorized_snapshot` boolean and actor/request audit data, but it does not create written legal approval. This is intentional: the real approval gate remains open and the system does not claim that a public page is authorized for automated use.

Disposition: retained as a visible Phase 2 boundary. A future approval workflow must bind imports to a persisted approval reference before any live polling is enabled.

### Medium — external persistence integration is unverified

Fresh SQLite migration round-trips pass. PostgreSQL/PostGIS and Redis could not be executed because Docker/Colima is unavailable in the environment.

Disposition: documented limitation; no production claim is made.

### Medium — local raw storage is an adapter, not production object storage

The storage abstraction currently uses immutable local files for development. Observation responses expose an opaque `local://` reference, and authorized users retrieve bytes through `GET /api/v1/retrievals/{retrieval_id}/raw`; filesystem paths are not exposed.

Disposition: Phase 2 local implementation is sufficient for reproducible tests. Production object storage and retention policy remain hardening work.

## Reviewer verification

The independent reviewer reported passing formatting/lint, mypy, parser/API tests, migration round-trip, schema-drift and zero-row checks, and scope review. The primary implementation run additionally passed the post-review 14-test suite, repository verification, API smoke test, live application health/readiness checks, and one-time parsing of the current official Sarasota HTML response. The final Luna confirmation found no critical or high implementation findings after the concurrency fixes. The final commands are recorded in the Phase 2 handoff.

## Review decision

No unresolved implementation critical/high defect remains. Phase 2 is ready for controlled handoff and commit, conditional on the explicitly open external approved-snapshot evidence gate. Phase 3 is not approved or started.
