# Dashboard redesign handoff — 2026-08-19

## Outcome

The authenticated web workspace was redesigned as an incident command ledger focused on finding, understanding, and reviewing records quickly. The prior presentation-style command center, unbounded incident stream, icon-only mobile navigation, decorative source/map graphics, and read-triggered scoring/matching behavior were replaced with bounded queues, direct evidence surfaces, labelled navigation, and explicit audited actions.

The complete diagnosis, information architecture, screen specifications, responsive contract, mutation-safety requirements, implementation sequence, and acceptance gates are in `docs/execution/dashboard-redesign-plan.md`.

## Implemented access improvements

- Grouped navigation into Review, Intelligence, and System destinations.
- Added a labelled native mobile view selector with all eight destinations.
- Rebuilt Review Desk around four operational metrics, an eight-row priority queue, and the selected incident workbench.
- Added incident search, provider/review filters, ordering, selected-row semantics, and 50-row pagination.
- Split mobile/tablet incident list and detail into separate states with a visible Back control and scroll-to-detail behavior.
- Rebuilt Opportunities as a 50-row decision table with search, evidence-tier, alert-posture, and order controls.
- Moved controlled snapshot import into Sources and Health and added a 25-row retrieval ledger.
- Replaced the decorative pseudo-map with explicit coordinate evidence and a no-inference empty state.
- Added Public Sans and IBM Plex Mono, squared ledger geometry, cold operational colors, clear focus outlines, and higher-contrast text.

## Mutation and governance checks

- Opening an incident now performs detail, property-match, score, assignment, and note GET requests only.
- Reload Data performs only persisted-data GET requests and states that no match or score changed.
- Property matching and opportunity scoring remain explicit audited actions.
- Incident state changes expose only valid transitions and require a visible reason before Save.
- Provenance, acquisition mode, confidence, abstention, hard gates, human review, and the no-outreach boundary remain visible.
- No source, scoring, model, outreach, or deployment scope was expanded.

## Browser verification

Authenticated local verification ran with Sarasota, Miami-Dade, and Broward polling workers disabled to prevent background writes.

- Desktop Review Desk rendered exactly eight priority rows and an adjacent selected workbench.
- Incidents rendered 50 of 2,045 matching rows; Opportunities rendered 50 of 71; retrieval history rendered 25 rows.
- Opportunity selection navigated to the matching incident workbench.
- Sources and Health exposed controlled import, provider health, and the provenance ledger.
- API logs for opening an incident contained only GET requests; Reload Data produced zero POST, PATCH, or DELETE requests.
- At an exact CSS viewport of 390 by 844, all eight navigation options were present, selected incident detail replaced the queue immediately, Back restored all 50 rendered rows, and visible incident rows were zero while detail was open.
- At 390 pixels, document width equalled viewport width on Incidents and Opportunities, all visible controls were at least 40 pixels high, and the visible-text contrast audit returned no normal-text failures below 4.5 to 1.

## Verification record

- `./scripts/verify.sh` — passed: 87 tests, formatting, Ruff, mypy, web lint, type validation, and Next.js production build.
- `python scripts/dev.py migrate` — the shell has no `python` alias, so this spelling could not start.
- `./.venv/bin/python scripts/dev.py migrate` — passed with the repository virtual environment.
- `./.venv/bin/python scripts/dev.py api-smoke` — passed against the safe local API runtime.
- `npm run lint` and `npx tsc --noEmit` in `apps/web` — passed during incremental and final checks.
- `git diff --check` — passed for the working tree.

## Known limitations

- The client still loads all provider pages before applying local filters; only rendered rows are bounded. Server-backed filtering can be added later if ledger size makes initial loading materially slow.
- Workflow and property-decision reasons outside the redesigned incident state/assignment/note controls still use the existing prompt interaction.
- No production deployment was performed.
