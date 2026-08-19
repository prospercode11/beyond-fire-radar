# Opportunity scoring abstention repair handoff

Date: 2026-08-19

## Outcome

The scoring pipeline was running for all 71 eligible fire opportunities, but several Broward rows were being blocked by property-matching and stale-contradiction defects. The repaired live projection now has 29 numeric scores, up from 17. The remaining non-numeric rows are explainable from current source evidence or the existing negative-source policy.

| Result | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| Numeric score | 17 | 29 | 12 rows recovered |
| Property evidence uncertain | 36 | 26 | 10 false matcher abstentions removed |
| Contradictory incident evidence | 2 | 0 | stale historical contradiction blocks removed |
| Negative-source suppression | 16 | 16 | unchanged governed policy |
| Total current opportunities | 71 | 71 | no eligible row was missing a scoring run |

Provider outcome after the v10 refresh:

| Provider | Scored | Evidence abstention | Policy suppression |
| --- | ---: | ---: | ---: |
| Broward | 13 | 0 | 7 |
| Miami-Dade | 0 | 19 | 2 |
| Sarasota | 16 | 7 | 7 |

## Bugs repaired

- Numeric ordinal streets such as `33rd` did not align with tax-roll `33`.
- A single address such as `3021` did not match a containing tax-roll range such as `3001-3161`.
- Removing the municipality globally corrupted a street with the same name, such as `Hollywood Blvd, Hollywood`.
- Exact unit evidence could be rejected because geocoder and tax-roll municipality labels differed even when address and coordinates agreed.
- Broad candidates could fill the 500-row cap before coordinate or reparsed exact-address candidates were considered.
- Multi-unit sites with an exact building address could not contribute a score without guessing an individual owner. They now use reduced building-level context, visibly withhold owner attribution, and remain alert-ineligible.
- Append-only historical contradiction evidence was incorrectly treated as a permanent current hard gate after current grouped observations became consistent.
- Tests disabled only the original Sarasota worker; enabled Miami-Dade/Broward settings could launch live workers during an isolated test run.
- The active release now uses immutable `address-normalization.v3`, `property-match.v5`, and `opportunity-scoring.v10`; older registered releases were not mutated.

## Remaining genuine boundaries

- 23 current source locations are blocks, intersections, highway/approximate locations, or otherwise too imprecise to select a parcel: 19 Miami-Dade and four Sarasota.
- Two Sarasota exact addresses remain in human review because the top parcel is not sufficiently separated from alternatives.
- One Sarasota exact multi-unit address remains unit-ambiguous and does not satisfy the safer building-level site rule.
- Sixteen rows remain suppressed under the existing negative-source policy for vehicle, brush, outside, or similar source wording. That is a scoring-policy choice, not a runtime failure, and was left unchanged.

## Verification

- `./scripts/verify.sh`: passed with 90 tests, formatting, Ruff, mypy, web lint/type validation, and Next.js production build.
- `./.venv/bin/python scripts/dev.py migrate`: passed.
- `./.venv/bin/python scripts/dev.py api-smoke`: passed before and after the live refresh; the post-write audit-chain integrity check passed.
- Controlled refresh: HTTP 200 with `{"rescored":71}`.
- Immediate unchanged refresh: HTTP 200 with `{"rescored":0}` in about six seconds.
- Live `3816 Hollywood Blvd` result: `site_matched`, six unit parcels, provisional score `66.5`, no individual owner attribution.

The first matcher-v5 refresh took about 21.6 minutes on the approximately 30 GB local SQLite database because all v4 matches were intentionally invalidated. PostgreSQL remains the production concurrency and throughput boundary.
