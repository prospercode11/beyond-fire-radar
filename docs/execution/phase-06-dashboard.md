# Phase 6 — Dashboard

Status: complete for the internal/local review workflow gate on 2026-08-01.

## Scope

Command Center, Incident Stream, map, workbench, property intelligence, opportunity pipeline, data health, settings, responsive navigation, and loading/error/empty states.

## Gate

Desktop/mobile/keyboard/visual inspection passes; uncertainty and freshness are visible; no sensational or misleading score language remains.

## Delivered

- Added a responsive internal dashboard shell with Command Center, Incident Stream, Opportunities, Data Health, and Settings views.
- Added explicit command-center surfaces for the review queue, source posture, incident map, evidence workbench, and property context.
- Kept the UI source-specific: Sarasota County manual snapshots are labeled throughout, live Sarasota polling is visibly disabled, and no approval or legal status is inferred.
- Added safe loading, API-unavailable, and empty states. The browser does not fabricate incidents, opportunities, map points, property candidates, or scores.
- Added provenance/uncertainty copy for provisional rankings and human-review requirements. Probability, damage, coverage, claim-validity, and outreach language is not used as an operational claim.
- Added responsive navigation with accessible button names, visible focus treatment, keyboard activation, and a mobile layout without horizontal overflow.
- Kept the browser as a presentation layer. The API remains the authorization boundary; no new backend data or source integration was added in this phase.

## Verification evidence

- `npm --prefix apps/web run lint && npm --prefix apps/web run build` passed; Next production build generated route `/` at 5.47 kB and first-load JavaScript at 108 kB.
- Browser inspection passed at the default desktop viewport and at 390×844: the required map/workbench/property surfaces are present, all five navigation buttons are discoverable, and measured document width was 375px with scroll width 375px.
- Keyboard navigation was exercised through the browser controls; navigation buttons have unique accessible names and active-view content changes.
- API-unavailable behavior was inspected and correctly showed a safe empty state with an explicit retry action.
- The repository verification contract, migration check, and clean isolated API smoke were rerun after the dashboard changes; final outputs are recorded in the Phase 6 handoff.

## Boundaries carried forward

No live Sarasota polling, Boca, Broadcastify, property ingestion, address-to-parcel matching, new scoring/model work, notifications, consumer outreach, or production dashboard deployment was started. The map is a source-preserving UI surface with no live GIS feed or inferred points.
