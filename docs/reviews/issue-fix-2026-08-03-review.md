# Independent review — Sarasota issue-fix pass

Date: 2026-08-03
Reviewer: independent Luna read-only review agent `019fc605-0b3d-7532-8a2a-7227d6e681fc`

## Initial findings

Luna found no Critical findings, five High findings, and three Medium findings. The findings covered reused source-event IDs at the same address, upload-to-score refresh behavior, silently swallowed property errors, historical property-import provenance, reproducibility of the legacy duplicate repair, UI provenance detail, timezone display, and missing real-Sarasota/browser regression evidence.

## Remediation recorded

- Reused event identifiers more than five minutes apart are now a deterministic non-match even at the same address; exact-time alternate agency case numbers remain supported. A regression test covers the 30-minute same-address reuse case.
- Property upload now performs match and opportunity rescore in sequence; selecting the current snapshot does the same. Snapshot-loading and non-404 match/score failures surface in the workspace rather than being silently converted to empty state.
- New property matches reject a non-current import, preventing a historical import label from being paired with the current parcel projection. A regression test covers the guard.
- The current snapshot panel displays acquisition mode, authorization basis, and content-hash prefix. Browser verification confirmed the 324,924-row Sarasota snapshot and parcel `0758080452`.
- `scripts/repair_sarasota_duplicate_incidents.py` provides a deterministic, dry-run-first exact source-event/location/UTC-time repair path. It recorded five legacy audited merges; a subsequent dry run found no groups.
- Browser date rendering explicitly treats timezone-naive API timestamps as UTC. Full verification, migration, API smoke, isolated E2E, Sarasota replay, and browser checks passed.

## Severity disposition

All initial Critical and High findings were addressed. The Medium findings were also addressed in code or verification evidence. The Sarasota external approval/source-terms gate remains open; no legal permission or source license is inferred.

Final post-remediation Luna confirmation: Critical 0, High 0. The documentation wording and dedicated exact-key revalidation test were addressed in this closure commit; the final verification run passed 67 tests.
