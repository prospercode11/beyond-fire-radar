# Phase 6 handoff — internal dashboard foundation

Date: 2026-08-01
Scope: Phase 6 only. Phase 7 has not started.

## Outcome

Phase 6 is complete for the internal/local dashboard gate. The responsive Next.js shell now provides:

- Command Center with review queue, source posture, source freshness uncertainty, API posture, and review principles.
- Incident Stream with a source-preserving empty state.
- Opportunities with an explicit provisional, non-probability research-ranking notice and safe not-loaded state.
- Data Health with manual-only Sarasota posture, API status, and disconnected external-service states.
- Settings with visible live-polling, outreach, probability-language, and human-review governance boundaries.
- Incident map, evidence workbench, and property-context surfaces with honest empty/not-loaded states.
- Desktop/mobile navigation, visible focus treatment, keyboard activation, responsive layout, and loading/API-unavailable/empty states.

The UI names Sarasota County manual snapshots as the current source posture. Live Sarasota polling remains disabled. No approval, legal status, live map point, incident, property candidate, score, damage finding, coverage opinion, claim-validity conclusion, or outreach recommendation is invented by the browser.

## Verification record

From the repository root:

```text
./scripts/verify.sh                         PASS
PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py migrate  PASS
API_BASE_URL=http://127.0.0.1:8000 \
DATABASE_URL=sqlite:///./data/phase5-api-smoke-final-20260801.db \
RAW_SNAPSHOT_DIR=./data/phase5-api-smoke-final-raw \
BOOTSTRAP_ADMIN_EMAIL=admin@example.com \
BOOTSTRAP_ADMIN_PASSWORD=change-me-in-development \
PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py api-smoke  PASS
npm --prefix apps/web run lint && npm --prefix apps/web run build  PASS
```

`./scripts/verify.sh` completed with 34 tests passed, Ruff, mypy, ESLint, and the Next production build passing. The final web build generated route `/` at 5.83 kB and first-load JavaScript at 108 kB. Migration was already at head. API smoke passed against the clean isolated SQLite database used for the Phase 5 evidence run; no stale local fixture provenance was mutated.

Browser verification passed in the Codex in-app browser:

- Default desktop visual inspection showed the command center, source posture, protected manual-only banner, API-unavailable safe state, and required dashboard surfaces.
- At 390×844, the measured document width was 375px and scroll width was 375px; no horizontal overflow was present.
- All five primary navigation buttons had unique accessible names. Incident Stream navigation changed the active view.
- Workbench tabs are native keyboard-operable buttons with controlled selection, tabpanel semantics, and arrow/home/end navigation.
- Browser tabs were finalized after inspection and the local web server was stopped.

Independent Luna review is recorded in [phase-06-dashboard-review.md](../reviews/phase-06-dashboard-review.md). The final pass found no unresolved critical or high-severity findings after remediation.

## Boundaries and limitations

- Sarasota remains the only initial source. No Boca radio, Broadcastify, or live polling was added.
- The external-source approval gate remains intact; manual availability is not treated as legal approval.
- No live GIS/map feed, authenticated dashboard domain-read workflow, production deployment, or new database schema was added.
- PostgreSQL/PostGIS and Redis integration could not run because Docker/Colima is unavailable on this host; this remains an external integration gate.
- The UI is not production authorization. The API remains the authorization boundary.

## Documents updated

`docs/execution/current-state.md`, `docs/execution/master-checklist.md`, `docs/execution/phase-06-dashboard.md`, `docs/execution/autonomous-v1-progress.md`, `docs/testing/evaluation-plan.md`, `docs/data/data-dictionary.md`, `docs/data/source-registry.md`, `docs/architecture/system-context.md`, `docs/architecture/threat-model.md`, `README.md`, this handoff, and the independent review.

## Next controlled step

Phase 7 — outcomes and evaluation foundation. Stop here for Phase 6 scope; do not begin Phase 7 in this handoff.
