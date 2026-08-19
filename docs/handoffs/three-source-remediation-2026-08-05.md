# Three-source audit remediation handoff — 2026-08-05

## Result

All P0/P1 defects found in the completed three-source audit were remediated in
the local workspace. The repair preserves raw snapshots and historical score
runs; it does not manufacture property evidence, source approval, or an
alert-eligible score.

This is a remediation record, not a new claim that every live-source or
external-service acceptance gate has passed. In particular, it does not prove
legal approval or source licensing, empirical score accuracy, or two completed
authorized live-poll cycles.

## Defects corrected

- A retrieval with raw rows could be left unprocessed after a failure. Pending
  raw snapshots now resume before the next provider poll, retain the failure
  evidence, emit a recovery audit event, and can be inspected with
  `scripts/recover_dispatch_processing.py` (dry run by default).
- A classification refresh could leave a current opportunity score on a
  now-ineligible incident. The scorer now retires that current row while
  retaining score history and audit provenance.
- Broward dispatch incidents were omitted from the Property workbench's county
  routing. They now route to `broward.property_tax_roll` and show the governed
  import/abstention posture rather than a false "provider unavailable" state.
- Incident ordering is newest-first; incidents, opportunities, and provider
  retrieval history are paginated until exhaustion in the dashboard instead of
  depending on one first page.
- Data Health now exposes retained-but-unprocessed retrievals and accepted row
  counts, plus parser/rejection/failure detail, rather than showing a healthy
  green state while evidence is awaiting processing.
- The worker loop schedules on start-to-start cadence, so a completed poll does
  not add a second 900-second wait. The lease remains the overlap guard.
- Known non-fire medical/public-service vocabulary is explicitly non-fire.
  Unsupported source wording is now labelled `Unknown source call`, which is
  safely non-scoreable rather than misleadingly labelled as an unknown fire.

## Current live-database evidence

Recorded on 2026-08-05 after automatic recovery of retained snapshots:

| Invariant | Result |
| --- | --- |
| Pending processed retrievals | 0 |
| Dispatch observations without a current incident link | 0 |
| Current score runs whose current source evidence is non-fire | 0 |
| Fire-only score reconciliation changes required | 0 |

`588 BOUNDARY BLVD` is present as Sarasota incident
`6935dad1-13f8-499f-941e-4d5a1678fced`, classified `Public service fire`. Its
one current score is correctly `abstained`, `alert_eligibility=false`, with
`property_match_uncertain`; no numeric score was fabricated.

`3884 NOTTINGHAM CIR` is also present as `Public service fire` with one current
`scored` run. Its `alert_eligibility` remains false; that state is a governed
review ranking, not a coverage or claim conclusion.

## Rendered UI evidence

- An isolated authenticated browser check loaded a Broward incident's Property
  tab and showed the Broward tax-roll source/provenance and its import-based
  workflow, not the former unavailable-provider message.
- The same check showed newest-first incident results and Data Health's
  retained-retrieval/accepted-row backlog state.
- After the production build, the local `http://localhost:3001/` dev shell was
  restarted to clear the Next build/dev cache collision. The rendered app now
  reaches its sign-in screen normally.

## Verification record

Working directory: `/Users/shalev/Documents/Beyond Claim Finder`.

| Command | Result |
| --- | --- |
| `./scripts/verify.sh` | Passed: Ruff format/check, mypy, **87 Python tests** in 344.45 seconds, web ESLint, and Next.js production build. |
| `./.venv/bin/python scripts/dev.py migrate` | Passed at the SQLite migration head on 2026-08-05T18:34Z. |
| `./.venv/bin/python scripts/dev.py api-smoke` | Passed on 2026-08-05T18:34Z. |
| `./.venv/bin/python scripts/recover_dispatch_processing.py` | Dry run: zero pending retrievals for Sarasota, Broward, and Miami-Dade. |
| `./.venv/bin/python scripts/reconcile_fire_only_scores.py --dry-run` | 49 current runs retained; zero reclassified, deactivated, rescored, or generated. |

Post-build browser verification initially exposed a stale Next development
manifest. Restarting only the local web development shell resolved that cache
condition; it was not an application-data failure.

## Remaining boundaries

- The official Sarasota page, the third-party Broward aggregation, and the
  Miami-Dade active-calls page have different completeness/authority limits.
  Broward is not presented as an official record, and Miami-Dade is not treated
  as a historical ledger.
- PostgreSQL/PostGIS and Redis integration gates were not run because their
  local services were unavailable. They remain unverified, not passed.
- Property matching and scores remain governed review evidence. They do not
  establish coverage, claim validity, damage, outreach eligibility, or model
  accuracy.
