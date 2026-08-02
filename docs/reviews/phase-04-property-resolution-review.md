# Phase 4 — Property resolution independent review

Date: 2026-08-01
Reviewer: independent Luna review agent
Scope: Phase 4 implementation in the working repository; read-only review and disposable SQLite/API reproductions

## Initial findings and dispositions

The first review found six high-severity issues: rollback reconstruction used timestamp ordering; candidate generation was too narrow; required address classes were mishandled; authenticated provenance was not inspectable; concurrent current imports were not constrained; and adversarial coverage was incomplete. These were fixed before acceptance.

The focused re-review found two high-severity issues: rollback did not restore derived aliases/buildings, and source alternate aliases were discarded. These were fixed by rebuilding derived projections from immutable import lineage, persisting alternate aliases, and exposing current derived provenance.

A final focused review found no remaining critical or high-severity findings after full-import projection cleanup was added. The final reviewer confirmed that full replacement rebuilds aliases/buildings from accepted rows and rollback reconstructs the prior projection from explicit lineage.

## Verification evidence

- Focused property tests: `5 passed` after the final fixes.
- Full repository verification (`./scripts/verify.sh`): passed; Ruff formatting/lint, mypy, 26 tests, web lint, and production build all passed.
- Ruff and mypy on the Phase 4 files/application: passed.
- The reviewer reproduced and then verified fixes for XLSX column alignment, rollback replacement data, alias/building rollback, mixed-header ZIP files, unit/block/county-road normalization, and parcel provenance.
- The reviewer confirmed that the official property import rejects missing authorization attestation, synthetic fixture imports remain explicitly labeled, and live Sarasota polling remains disabled.

## Remaining non-release blockers

- Official Sarasota property-source approval/terms and an approved real snapshot were not supplied. The fixture cannot establish real-world property-match accuracy.
- PostgreSQL/PostGIS and Redis integration could not run because Docker/Colima was unavailable on the host. SQLite is the verified local path; production spatial/locking behavior remains unverified.
- Browser/dashboard inspection belongs to Phase 6; Phase 4 is an authenticated API/manual prototype surface.

## Release recommendation

Go for the local/manual Phase 4 gate only. Do not enable automated property retrieval, live Sarasota polling, or treat fixture results as production accuracy evidence.
