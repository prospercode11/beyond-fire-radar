# Three-source full audit prompt

Copy everything below this line into a new Codex task.

---

You are auditing the complete Beyond Fire Radar / Beyond Claim Finder system in:

`/Users/shalev/Documents/Beyond Claim Finder`

The audit must determine whether the app reliably checks the three intended dispatch pages, preserves every source row, creates the correct incidents, exposes every incident in the UI, and applies the governed property and opportunity-scoring workflow correctly.

This is an evidence-driven, read-only audit. Do not edit code, mutate the main database, merge incidents, reprocess production-like data, change configuration, start live polling, commit, push, deploy, or repair findings during the audit. Use an isolated temporary database for any test that writes data. Preserve the dirty worktree. If an issue is found, report it with a reproduction and repair plan. Do not fix it unless the user separately authorizes implementation.

## Exact dispatch sources

Audit these exact pages and provider IDs:

1. Sarasota County official dispatch
   - URL: `https://dispatchreporting.scgov.net/Events?strAgencyID=All`
   - Provider: `sarasota.official_dispatch`
   - Saved page: `/Users/shalev/Downloads/911 Dispatch Reporting _ Sarasota County, FL.html`
   - Saved assets: `/Users/shalev/Downloads/911 Dispatch Reporting _ Sarasota County, FL_files/`

2. Broward County dispatch aggregation
   - URL: `https://efirstalert.com/live-dispatch-for-broward-county/`
   - Provider: `broward.efirstalert_dispatch`
   - Saved page: `/Users/shalev/Downloads/Live Dispatch Broward County – eFirstAlert – First to know!.html`
   - Saved assets: `/Users/shalev/Downloads/Live Dispatch Broward County – eFirstAlert – First to know!_files/`
   - Treat this as a third-party eFirstAlert aggregation, not an official Broward County record.

3. Miami-Dade Fire Rescue active calls
   - URL: `https://www.miamidade.gov/firecalls/calls.html`
   - Provider: `miami_dade.fire_calls`
   - Saved page: `/Users/shalev/Downloads/MDFR CAD Active Calls.html`
   - Saved assets: `/Users/shalev/Downloads/MDFR CAD Active Calls_files/`
   - Treat this as an active-calls display, not a complete historical incident ledger.

The saved HTML files are reproducible golden snapshots. Live pages are a separate, time-stamped check and will naturally have different rows. Never compare a current live count to a saved count as if they should match.

## Mandatory operating rules

1. Read `AGENTS.md` completely before acting and obey the repository verification contract.
2. Begin with `git status --short`, `git diff --stat`, process/port discovery, current configuration, and database-path discovery. Do not overwrite or revert existing work.
3. Verify the actual API and web origins before browser testing. Do not assume port 3000 or 3001.
4. Use the existing parser/provider/ingestion code. Do not write a substitute parser and call that evidence.
5. Do not use synthetic fixtures as evidence of real source accuracy. Fixtures may only test deterministic mechanics.
6. Do not claim legal approval, source licensing, model accuracy, damage, insurance coverage, claim validity, or outreach eligibility.
7. Scores are provisional review rankings, not probabilities. Missing or ambiguous evidence must remain visible as an abstention or Review Only state.
8. Do not bypass CAPTCHA, access controls, rate limits, robots controls, or authentication. A normal HTTPS GET is the maximum allowed retrieval behavior.
9. Do not enable live polling when the repository approval/configuration gate is closed. In that case, inspect the saved captures and mark live polling as unverified, not passed.
10. Do not claim a check passed without recording the exact command, output, timestamp, and evidence.
11. If a required verification command fails, stop that acceptance gate and report the failure. Do not continue and later describe the overall audit as passed.
12. Keep external-service boundaries honest. Unavailable PostgreSQL/PostGIS, Redis, object storage, or live websites are unverified, not passed.

## Known snapshot baselines to independently reproduce

Do not trust these numbers blindly. Reproduce them using the current registered parsers and explain any difference:

| Source | Source rows in saved page | Current expected parser result | Expected visible issues |
|---|---:|---|---|
| Sarasota | 57 | 57 normalized rows | No parser issue in this capture |
| Broward | 39 | 39 normalized rows | No parser issue in this capture |
| Miami-Dade | 9 | 8 normalized rows | One `missing_location` row-level issue for a `02:40` `MEDICAL` row with units `E12 MIA1 R12` and no address |

The Miami row with no address must be preserved as an inspectable source/error record. It must not disappear silently and must not receive an invented address or property match.

Known taxonomy leads that require independent review:

- Sarasota `AIRCRAFT EMERGENCY` currently falls into an unknown family. Verify whether that is the safest supported classification and confirm that it cannot become a fire opportunity without explicit fire evidence.
- Broward `BACK PAIN`, `HEMORRHAGE OR LACERATION`, and `MENTAL ILLNESS` currently require review for whether they should map to the non-fire medical family instead of an unknown family. They must never become fires based on dispatched unit labels.
- `PUBLIC SERVICE FIRE`, `INVESTIGATE EXTINGUISHED FIRE`, and `ILLEGAL BURNING` must remain explicit fire families and score-eligible under the normal property-evidence gates.
- `588 BOUNDARY BLVD` must remain discoverable in Incidents, classified as `Public service fire`, score-eligible, and visibly abstained when the property match remains uncertain. Do not fabricate a numeric score.
- `3884 NOTTINGHAM CIR` must remain discoverable and score-eligible; independently verify its current score rather than assuming an old value is still current.

## Audit workstream 1: source acquisition and polling

For each provider, inspect configuration, provider registry metadata, approval gates, startup wiring, worker lifecycle, and failure handling.

Verify all of the following:

- The configured URL exactly matches the intended page above, including Sarasota query parameters and HTTPS.
- The response identity checks reject a generic error page, consent page, CAPTCHA page, login page, empty shell, or unrelated HTTP 200 page.
- Redirects are bounded and do not allow a provider URL to become a user-controlled SSRF path.
- Status codes, timeouts, response-size limits, encoding, decompression, and malformed responses fail visibly.
- Each provider can be independently enabled or disabled. Enabling one worker must not accidentally enable another.
- Development authorization and production/staging `LegalApproval` gates fail closed.
- Every enabled worker runs one controlled startup cycle and then uses the configured interval of exactly 900 seconds.
- The lease prevents overlapping cycles across threads/processes. Test lease expiry, worker crash, stale lease recovery, and two simultaneous poll attempts in isolation.
- A slow request cannot overlap the next cycle or create duplicate ingestion/score writes.
- Poll success, replay, skip, parse warning, schema drift, zero-row anomaly, HTTP failure, timeout, and unexpected-response outcomes update provider health truthfully.
- Failure counters and circuit state recover after a later valid response.
- Audit events record provider, acquisition mode, authorization basis, retrieval, processing run, counts, outcome, error, request ID, and timing without leaking secrets.
- Raw response bytes, content type, retrieval timestamp, content hash, and source URL/provenance are retained.
- A page that has not changed is an idempotent replay, not a duplicate incident batch.
- A changed page with some old and some new calls creates only the new evidence/links required.
- Active-call disappearance from a later page does not erase prior raw evidence or historical incidents.
- Broward's lack of a stable source incident ID and calendar date is clearly disclosed in metadata and UI.
- Miami-Dade's active-call incompleteness and approximate/variable address semantics are disclosed.

If normal live access is currently authorized by the existing local configuration, perform a time-stamped, read-only live comparison for two consecutive completed cycles. Do not alter configuration to obtain this evidence. Record retrieval start/end times, row counts, hashes, replay status, processing counts, provider health, and the exact new source rows that appeared. If authorization is not already present, mark this live-cycle check unverified.

## Audit workstream 2: HTML/table parser fidelity

Run all three saved HTML files through the registered parser versions. For every visible source table row, build a row-level reconciliation showing:

- source page and source table
- source row number
- raw source fields
- accepted or rejected status
- rejection code and message when rejected
- normalized observation ID if accepted
- original event wording
- normalized family
- original location
- event time in source local time and stored UTC
- source event ID and source case number when present
- generated deterministic identity when the source omits an ID
- station, jurisdiction, grid/zone, units, coordinates, and map link when supplied

The reconciliation invariant is:

`visible source rows = accepted normalized rows + visible row-level rejects`

There must be zero unaccounted rows.

Specifically test:

- Sarasota grouped event dates, all table headers, exact event/case identifiers, duplicate multi-agency rows, stations, grid values, midnight transitions, DST boundaries, and local-to-UTC conversion.
- Miami-Dade multiple regional tables, `RCVD`, `FC`, `INC_TYPE`, `ADDRESS`, `UNITS`, repeated headers, empty tables, missing addresses, cross-streets, block addresses, page date extraction, midnight transitions, and rows that move or disappear.
- Broward `Last Update`, `Original Call Time`, `Call Type`, `Jurisdiction`, `Address`, `Units Dispatched`, map links, coordinates, missing units, missing/parcel-like addresses, retrieval-date inference, midnight rollover, DST, stable generated IDs on identical reparse, and changed-row identity behavior.
- Nested tags, HTML entities, non-breaking spaces, duplicate headers, extra columns, reordered columns, renamed columns, missing required columns, multiple unrelated tables, empty `tbody`, malformed rows, very long values, Unicode, and browser-extension artifacts in saved HTML.
- The parser must not require CSS, JavaScript, images, local `_files` assets, Chrome-extension scripts, or network loading of saved-page assets to extract server-rendered table data.
- Schema drift must produce a warning/error and provider-health signal. It must not silently map columns by position.
- A zero-row parse must be a visible anomaly, not a successful empty update.
- Raw source wording must remain available after classification.

Enumerate every unique event type in all three captures and create a source-vocabulary matrix containing the source wording, normalized family, score eligibility, reason, count, and confidence that the mapping is source-supported. Explicitly flag every unknown family and every event type whose mapping relies on a broad substring rule.

## Audit workstream 3: ingestion, replay, and provenance

Using an isolated database and the saved captures, verify:

- Provider registration and parser/schema version selection are correct for each provider.
- Manual uploads require the correct attestation and remain labeled `manual_snapshot`; live cycles remain labeled `live_poll`; fixtures remain synthetic.
- The immutable raw snapshot, raw row, normalized observation, import job, retrieval, processing run, provider health, and audit records all link correctly.
- Content hashes and idempotency keys prevent duplicate ingestion without conflating different content.
- Reusing an idempotency key with different content fails visibly.
- Re-uploading identical bytes under another filename replays the same snapshot safely.
- Parser issues retain raw row payload, row number, code, and message.
- Accepted, rejected, and normalized counts reconcile at every layer.
- A processing failure cannot leave a retrieval falsely marked completed.
- Transaction rollback does not lose the error/health signal.
- Parser-version comparison and replay do not rewrite immutable historical evidence.
- Retention, backup, restore, and content-hash verification preserve all three providers' raw snapshots.
- HTML is treated strictly as data. Confirm that source-controlled text cannot execute in the API or dashboard and cannot cause stored XSS.

## Audit workstream 4: canonical incident assembly

For every accepted row in the saved captures, trace the observation into the current canonical incident decision. Reconcile counts by provider:

`accepted observations -> current observation links -> unique active incidents + intentional historical/non-current links`

Audit:

- Exact source event/case updates.
- Same-event multi-agency rows that should link to one incident while preserving both observations.
- Reused source event IDs, missing/alternate case numbers, same-address events at different times, and the five-minute reused-ID separation guard.
- The 90-minute same-agency/same-case update window.
- Address normalization without aggressive cross-incident merging.
- Anti-transitive-overmerge behavior where A resembles B and B resembles C but A and C are different events.
- Cross-county isolation. Sarasota, Miami-Dade, and Broward rows must never merge solely because normalized locations or generated IDs collide.
- Replays, late arrivals, reordered snapshots, contradictory event wording, event cancellation/update behavior, and active/inactive state transitions.
- Manual merge/split auditability and preservation of all source links.
- Current incident classification refresh when taxonomy versions change.
- No observation may be orphaned, linked to two current incidents, or silently deleted.
- Current incident counts and source counts must be queryable without relying on the first 500 records.

Produce an exceptions table for every row that did not create a one-to-one incident and explain why the linkage is correct or suspicious.

## Audit workstream 5: taxonomy and fire-score eligibility

Verify classification from current source observations, not only persisted incident labels.

Required invariants:

- Explicit source-supported fire families are score-eligible, including generic `FIRE`, structure/working fires, vehicle/brush fire families where policy permits, `PUBLIC SERVICE FIRE`, extinguished-fire investigation, and illegal burning.
- Routine alarms, crashes, medical calls, rescue, hazmat, gas odor, unsupported/unknown calls, mixed fire/medical calls, and opaque Broward call codes remain evidence-only and cannot enter Opportunities.
- Dispatched unit labels alone never promote an event to fire.
- Smoke or electrical wording is only score-eligible when the source text explicitly supports the configured fire/structural-exposure family.
- Every active score-eligible fire incident has exactly one current score run, even when that run is abstained.
- No active non-fire incident has a current opportunity row or alert-eligible score.
- Taxonomy refresh repairs stale projections without deleting source or score history.
- Fire-score gate/version evidence is present in the score explanation.

Build two complete database reports:

1. Active explicit-fire incidents with provider, location, source event type, classification, current score status, property match status, abstention reason, scoring version, source observation IDs, and opportunity-list presence.
2. Any current score/opportunity whose current source-derived family is not score-eligible. The required result is zero rows.

Explicitly regression-check `588 BOUNDARY BLVD`, `3884 NOTTINGHAM CIR`, generic `FIRE`, routine alarms, crashes, medical calls, mixed fire/medical calls, extinguished-fire investigations, illegal burning, and unknown source wording.

## Audit workstream 6: property resolution and scoring mechanics

Confirm county routing:

- Sarasota dispatch -> `sarasota.property_appraiser`
- Miami-Dade dispatch -> `miami_dade.property_appraiser`
- Broward dispatch -> `broward.property_tax_roll`

Audit the complete chain for every active explicit fire:

`current dispatch evidence -> current county property import -> match run -> candidate/abstention -> score run -> opportunity visibility`

Verify:

- Only the current property projection is used for new matching/scoring.
- Provider/import/source version, accepted-row count, acquisition mode, authorization basis, and content hash are visible.
- Exact address, unit, master parcel, street/house, municipality, ZIP, intersection, block, highway/route, landmark, coordinates, and malformed-location behavior.
- Five-digit house numbers are not mistaken for ZIP codes.
- Broward parcel-like address strings are not treated as valid street addresses without supporting evidence.
- Unit ambiguity, low source precision, no candidate, stale import, and insufficient score separation abstain visibly.
- No property is invented for source rows with missing/general/cross-street locations.
- Human confirmation/rejection/clear history remains visible after refresh.
- Scores retain component provenance, source observation IDs, scoring version, property import/match linkage, previous score history, and semantic warning that the score is not a probability.
- Missing/ambiguous property evidence produces a dash/abstention and Review Only behavior rather than a fabricated numeric rank.
- Repeated unchanged refresh uses completeness checks, returns no unnecessary rewrites, and preserves previous score history.
- Concurrent refresh/poll actions do not violate the one-current-score constraint or lock SQLite indefinitely.
- Alert eligibility remains false for live-poll or otherwise unauthorized evidence and for abstained/uncertain property matches.

Do not make any empirical accuracy claim unless there is a separately authorized, leakage-controlled, representative ground-truth dataset. Mechanical correctness and snapshot reconciliation are not model-accuracy evidence.

## Audit workstream 7: API and dashboard completeness

Test the running app through its real API and rendered UI, including desktop and narrow/mobile widths.

Verify:

- Authentication, session expiry, role checks, and API errors are visible.
- Each provider's incident list paginates independently until exhaustion; results are merged and ordered correctly.
- The UI does not silently cap the ledger at 500 records.
- Exact-address searches find old and new incidents from all three providers, including `588 BOUNDARY BLVD`.
- Every API incident can be opened from the rendered Incident Stream and displays the correct provider, original source evidence, timestamps, classification, score eligibility, property state, and current score/abstention.
- Provider filters, county labels, loading, empty, unavailable, retry, and stale-response states are truthful.
- Opportunities contain every current explicit fire score run and no non-fire incidents.
- Abstained fire opportunities remain visible with the reason and no fabricated score.
- Refresh is idempotent, reports progress/errors, and does not leave the page stuck.
- Data Health reports last retrieval, freshness, row counts, parser/schema versions, warnings, failures, circuit state, authorization posture, and polling state for all three providers.
- Saved/manual/live/synthetic provenance is not mislabeled.
- Broward is clearly marked third-party and Miami-Dade clearly marked active-calls-only.
- Detail navigation, back/forward navigation, keyboard access, focus, responsive layout, and no-horizontal-overflow behavior work.
- Browser evidence includes screenshots of each provider in the stream, a fire detail, a non-fire detail, an abstained score, Data Health, and at least one error/empty state.

Do not accept source-code handler existence as UI proof. Verify actual rendered clicks and route/view transitions.

## Audit workstream 8: API, database, security, and operations

Inspect and test proportionately:

- API pagination bounds, ordering stability, filtering, input validation, upload limits, content-type handling, request-size limits, and error codes.
- Database uniqueness/current-row constraints, foreign keys, indexes, migration ownership, UTC handling, and transaction boundaries.
- Poll/refresh concurrency, SQLite lock behavior, and PostgreSQL production assumptions.
- Stored XSS from event type, address, station, jurisdiction, units, filenames, and provider error text.
- SSRF/open redirect risks, untrusted HTML parsing, archive/path traversal, symlink handling, raw-file access controls, and object-storage key construction.
- Authentication/session replacement, rate limiting, trusted hosts, security headers, CORS/origin handling, logs, metrics cardinality, and secret redaction.
- Tamper-evident audit-chain verification for retrieval, import, processing, merge/split, property, score, override, assignment, export, suppression, and status transitions.
- Backup/restore includes database plus raw snapshots and verifies hashes.
- Retention is dry-run-first, audited, and failure-safe.
- Readiness does not claim Redis/PostgreSQL/object storage healthy when unavailable.
- No external notification or consumer outreach path is enabled.

## Audit workstream 9: adversarial and regression testing

Confirm existing tests cover the real contracts and add a gap list for anything missing. In an isolated test environment, exercise at minimum:

- Valid saved snapshot for each provider.
- Identical replay, same idempotency key/different bytes, changed snapshot, row reorder, and partial overlap.
- HTTP 200 error page, 403/429/500, timeout, redirect, oversized response, truncated HTML, invalid encoding, no table, empty table, and unrelated table.
- Required-column removal, column rename/reorder/addition, duplicate headers, multiple regional tables, malformed row, and missing address.
- Midnight before/after retrieval, previous-day inference, DST spring/fall transitions, and naive/aware timestamp handling.
- Duplicate multi-agency Sarasota event, reused IDs, alternate case number, late update, and anti-transitive incident linkage.
- Broward generated-ID stability and collision resistance without a source ID/date.
- Generic fire, structure fire, public service fire, extinguished fire, illegal burning, smoke, alarm, medical, crash, rescue, hazmat, mixed fire/medical, blank, opaque one-letter, and unknown call types.
- Missing/current/stale property imports, exact/unit/intersection/block/route matches, ambiguity, human decisions, and stale rematch.
- More than 500 incidents per provider, all-page UI loading, exact-address search, detail click, and opportunity exclusion/inclusion.
- Two simultaneous polls, poll plus refresh, stale lease, database contention, retry, and unchanged refresh performance.
- Raw snapshot tampering, backup/restore, audit-chain tampering, session expiry, role denial, rate limit, and stored-XSS payloads.

## Required commands and acceptance evidence

After all read-only inspection and isolated tests, run the repository contract from the repository root:

```bash
./scripts/verify.sh
./.venv/bin/python scripts/dev.py migrate
./.venv/bin/python scripts/dev.py api-smoke
```

Also run the relevant isolated end-to-end acceptance command and browser checks. If a required external dependency is unavailable, state exactly which test was skipped and why. A skipped dependency is not a production pass.

Record:

- command
- working directory
- start/end timestamp
- exit code
- test count
- skipped tests and reasons
- warnings
- exact failure output

## Non-negotiable acceptance gates

The overall audit may be marked `PASS` only if all of these are demonstrated:

1. All visible saved-page source rows reconcile to accepted observations or visible row-level rejects, with zero silent loss.
2. All accepted observations have preserved raw provenance and a valid current/historical incident-link explanation.
3. Replays and overlapping snapshots do not create duplicate evidence or incidents.
4. Current source-derived classifications are source-faithful; every unknown is listed and safely non-scoreable.
5. Every active explicit fire has exactly one current score run or visible governed abstention.
6. No non-fire incident appears as a current opportunity or alert-eligible score.
7. County property-provider routing is correct and unresolved property evidence never produces an invented match/score.
8. Every incident is reachable through API pagination and rendered UI; no global first-page cap hides newer incidents.
9. Provider health, freshness, schema warnings, failures, polling state, and authorization posture are truthful for all three sources.
10. Polling is independently gated, lease-protected, exactly 900 seconds when enabled, and auditable.
11. Required formatting, lint, type, unit, integration-available, build, migration, API-smoke, and relevant browser tests pass.
12. No P0/P1 finding remains, and no required area is merely assumed.

If any gate lacks evidence, use `CONDITIONAL` or `FAIL`, not `PASS`.

## Required final report format

Lead with one verdict: `PASS`, `CONDITIONAL`, or `FAIL`.

Then provide:

1. **Executive conclusion**: what is trustworthy, what is broken, and what remains unverified.
2. **Three-source reconciliation table**: source rows, accepted, rejected, observations, unique active incidents, explicit fires, current score runs, and unaccounted rows.
3. **Live polling table**: configured URL, enabled state, authorization decision, last attempt/success, freshness, interval, lease, normalized count, health, and evidence timestamp.
4. **Findings**, ordered P0 to P3. Every finding must include:
   - severity
   - confidence
   - affected provider(s)
   - user impact
   - exact evidence and timestamp
   - reproduction command/steps
   - file and line references
   - root cause
   - smallest safe repair
   - regression test required
5. **Row-level exceptions**: every missing, rejected, duplicated, ambiguously linked, unknown-classified, score-missing, or UI-hidden row.
6. **Scoring integrity report**: all explicit fires and any forbidden non-fire current score rows.
7. **UI/browser evidence** with screenshots and exact origin tested.
8. **Verification command results** with skips and external dependency boundaries.
9. **Prioritized repair plan** grouped into immediate data-integrity fixes, correctness regressions, reliability/security work, and lower-priority improvements. Do not implement it during this audit.
10. **Known limitations**: source incompleteness, third-party status, authorization, property-data limitations, and why this audit does not establish legal approval or empirical model accuracy.

Be candid. “No issue found” is acceptable only after the corresponding acceptance evidence exists. A parser test alone is not end-to-end proof; a database row alone is not UI proof; a successful build alone is not live-poll proof.

---
