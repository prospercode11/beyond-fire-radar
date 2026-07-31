# Independent Luna review — Phase 3 incident intelligence

Date: 2026-07-31
Reviewer: Luna (independent read-only review)
Scope: Phase 3 requirements, master specification, working-tree implementation, migrations, linkage/state/provenance behavior, tests, and scope control.

## Initial findings and disposition

Luna's independent review returned no critical findings and five high-severity findings:

| Finding | Disposition |
| --- | --- |
| Concurrent processing could race on current observation assignment and processing-run creation | Fixed with a database-unique current assignment key, unique source-record identity index, explicit flushes around reassignment, and retrieval processing-run collision recovery. |
| Acquisition mode default could misclassify a future retrieval as manual | Fixed by removing the model/database default for new retrievals in migration `0005_incident_integrity_controls`; ingestion supplies the mode explicitly and processing accepts only known manual/fixture modes. |
| Kept-separate explanations were not reliably returned on the newly created incident | Fixed by returning decisions for the incident's current observations as well as candidate decisions. |
| Classification/contradiction state history and alert-revocation evidence were incomplete | Fixed with classification-change timeline events and persisted review-signal issue/revocation status, timestamps, and reason when contradiction rescoring revokes a high-confidence signal. |
| Review/handoff evidence was incomplete and verification was environment-sensitive | Fixed by adding this review, the Phase 3 handoff, rerunning formatting/lint/types/tests/migrations/API smoke/web build, and making `scripts/verify.sh` select the repository venv. |

Luna's post-fix confirmation then identified two additional high-severity upgrade/concurrency risks: cross-retrieval source identity races and `0005` uniqueness indexes failing on valid `0004` duplicate state. These were fixed with provider-scoped database serialization, source-identity reconciliation, migration deduplication/collision preservation, and a concurrent cross-retrieval regression test. A later confirmation found provider scope was required for source identities; migration `0006_scope_incident_aliases_by_provider`, provider equality checks, and a cross-provider regression test closed that finding. The final confirmation found and closed one downgrade-chain index restoration issue; the complete `0006 → 0005 → 0004 → 0003` downgrade path and re-upgrade now pass with cross-provider duplicate identities preserved as an explicit collision on downgrade.

## Adjacent completeness fixes

The review also identified missing master-spec responder/disposition tables and broad edit-role access. Phase 3 now includes `responding_agencies`, `responding_stations`, and `incident_dispositions` (the latter remains empty unless source-supported disposition evidence is supplied), and state/merge/split editing is restricted to administrator or analyst roles. No researcher or live-source privilege was invented.

## Verification after fixes

- `./scripts/verify.sh`: passed — 20 tests, Ruff format/check, mypy, web lint, and Next.js production build.
- A migration upgrade from a deliberately duplicated valid `0004` incident state passed through `0006`; the migration retained the oldest current assignment, preserved later source-record collisions as explicit collision aliases, and populated provider-scoped identity before creating unique indexes.
- Fresh SQLite `upgrade head`, `downgrade 0005_incident_integrity_controls`, and `upgrade head`: passed through migration `0006_scope_incident_aliases_by_provider`.
- Full SQLite downgrade chain `head → 0004 → 0003`, including two providers with the same source ID, passed; the chain preserved one source ID plus one explicit collision, removed Phase 3 tables at `0003`, and re-upgraded to head.
- Isolated application startup and `scripts/api_smoke.py`: passed with live polling false, fixture acquisition labeled `synthetic_fixture`, and replay stable.
- Phase 3 API tests: passed for Sarasota replay, duplicates, missing IDs, conflicting types, reused identifiers, separate same-address fires, malformed records, incremental contradiction/rescore, state transitions, merge, and split.

## Residual limitations

PostgreSQL/PostGIS and Redis integration execution was not possible because Docker/Colima is unavailable on this host. The local SQLite path is verified; this is not represented as production integration approval. Live Sarasota polling, Boca/Broadcastify, property resolution, scoring, dashboard, outreach, and learned models remain out of scope.

## Review conclusion

After the fixes above, no unresolved critical or high-severity implementation finding remains for the Phase 3 local/manual prototype boundary. Phase 3 is ready for handoff and commit. Phase 4 must not begin from this change.
