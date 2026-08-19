# Dashboard redesign plan — incident command ledger

## Objective

Replace the presentation-style dashboard with an operational review workspace where an internal reviewer can quickly find the next relevant incident, understand its evidence and blockers, and complete an auditable review without losing context.

This redesign changes information architecture, visual hierarchy, and interaction design. It does not weaken provenance, abstention, legal/source gates, human-review requirements, audit history, or the prohibition on automatic consumer outreach.

## Verified problems in the current interface

1. The Incident Stream renders every loaded incident. The verified local ledger produced 2,045 rows and a document more than 130,000 pixels tall.
2. At 390 by 844, incident detail is placed after the entire list. A selected record begins roughly 125,000 pixels below the top of the page.
3. Opening an incident can automatically create a property-match run and rescore. Read navigation and audited mutations are not separated.
4. The controls labelled Refresh invoke the fire-score repair/rescore endpoint instead of performing a passive reload.
5. The command center gives similar visual weight to metrics, imports, source posture, principles, an empty map, and the review queue.
6. Opportunities are a long list without decision-oriented filters or columns.
7. Operational text is commonly 9 to 11 pixels and several muted colors do not meet normal-text contrast targets.
8. Mobile navigation hides labels and requires horizontal scrolling to reach all eight destinations.
9. Rounded white cards, pills, a cream/green palette, generic Arial typography, and decorative source/map graphics make the product feel templated rather than purpose-built.

## Chosen design direction

The visual reference is an incident command ledger: county dispatch terminals, structured incident reports, and evidence logs.

- Color: cold white and cool gray surfaces, deep midnight navigation, evidence blue for selection/provenance, fire red only for urgent fire attention, and amber only for uncertainty or blocked states.
- Type: Public Sans for readable public-sector operations UI and IBM Plex Mono for timestamps, versions, IDs, and numeric evidence.
- Shape: squared 2 to 4 pixel corners, ledger rules, almost no shadow, and rectangular status labels rather than pills everywhere.
- Density: compact but readable, with 13 to 15 pixel operational text and 40 to 44 pixel controls.
- Layout: bounded queues and independently accessible detail, not one document containing every record.
- Copy: direct operational labels such as Review desk, Incident queue, and Sources and health.

## Information architecture

### Review

- Review desk
- Incidents
- Opportunities
- Workflow

### Intelligence

- Outcomes

### System

- Sources and health
- Model lab
- Settings

The Review Desk contains the attention summary, a short prioritized queue, and the selected incident. Snapshot import and detailed provider posture move to Sources and Health.

## Screen specifications

### Review desk

- Compact title and current runtime/source posture.
- Four decision metrics: active incidents, needs attention, current opportunities, and source freshness.
- Prioritized incident queue with a maximum of eight rows.
- Selected incident workbench beside the queue. Selecting a row exposes its detail without changing data.
- If nothing is selected, show an operational empty state that explains what to select.
- No decorative source orbit, review-principles card, or empty pseudo-map.

### Incident queue

- Desktop: fixed two-pane layout with an independently scrolling list and detail pane.
- Mobile/tablet: the list and detail are separate states. Selecting a row opens detail immediately; Back to incident queue restores filters and page.
- Search plus provider, classification, and attention filters.
- Sort newest/oldest and a bounded 50-row page.
- Page range and previous/next controls.
- Selected-row state and accessible current-item semantics.
- Opening a row performs GET requests only.

### Incident workbench

- Header: location, classification, confidence, current state, source mode.
- Tabs: overview, evidence, property, score.
- Overview emphasizes event window, classification, retained evidence, source provenance, and coordinate evidence.
- State changes show only current and valid next states. A visible reason field is required before saving.
- Property matching and score generation remain explicit buttons with clear audited-action wording.
- No automatic property match or score refresh on selection.

### Opportunities

- Search, evidence-tier filter, eligibility filter, and score/date sorting.
- Table-style rows with rank, incident, jurisdiction/source, evidence tier, hard gate, alert eligibility, and as-of time.
- Headline rank rounded to one decimal; the exact versioned value remains available in detail.
- Bounded 50-row page.
- Selecting a row opens the matching incident and its workbench.

### Workflow, outcomes, model lab, settings

- Preserve all existing behavior and boundaries.
- Reapply the ledger visual system and readable typography.
- Notification control navigates to Workflow instead of acting as a dead control.

### Sources and health

- Provider health and retrieval status remain visible.
- Controlled dispatch import moves here.
- Runtime polling state is distinguished from historical acquisition mode.
- Import attestations and legal/source caveats remain intact.

## Responsive behavior

- At 900 pixels and below, queue/detail becomes a single active surface.
- At 720 pixels and below, replace the icon-only scrolling navigation with a labelled native view selector containing every destination.
- Selected incident detail appears immediately and never follows the complete queue in document order.
- No horizontal page overflow at 390 pixels.
- Touch targets are at least 40 pixels high; primary controls target 44 pixels.
- Supporting text is at least 12 pixels; normal operational text is at least 13 pixels.

## Mutation-safety requirements

- Reload data: GET-only workspace reload.
- Match current property snapshot: explicit POST initiated by its labelled button.
- Generate/rescore opportunity: explicit POST initiated from the Score tab.
- State transitions: explicit reason plus Save state change.
- Workflow mutations continue to require a reason and remain audited.
- The UI must never call property matching or scoring merely because a record was opened.

## Implementation sequence

1. Add the font and visual token foundation.
2. Rework the application shell and labelled responsive navigation.
3. Make workspace reload read-only and load the authenticated user.
4. Rebuild Review Desk and move controlled import to Sources and Health.
5. Add bounded incident filtering, pagination, selected state, and mobile list/detail navigation.
6. Rework workbench state changes and replace the empty pseudo-map with coordinate evidence.
7. Rebuild Opportunities as a filtered decision table.
8. Apply the ledger system to secondary views and confirm all existing empty/error/loading states.
9. Run repository, browser, accessibility, responsive, and anti-vibe verification.

## Acceptance gates

- A selected incident is visible immediately at desktop, tablet, and 390 by 844 mobile sizes.
- No page renders more than 50 incident or opportunity rows at once.
- Opening an incident produces no POST, PATCH, or DELETE request.
- Reload workspace produces no scoring, matching, workflow, or state mutation.
- Every navigation destination is labelled and reachable without horizontal guessing.
- Score summary values do not clip at 1024 or 390 pixels.
- No page has horizontal overflow at 390 pixels.
- Normal text contrast meets 4.5 to 1; large text meets 3 to 1.
- Provenance, source mode, authorization posture, abstention, confidence, hard gates, and human review remain visible.
- Fixture data is never presented as real-world accuracy or legal/source approval evidence.
- No outreach capability is introduced.
- `./scripts/verify.sh`, `python scripts/dev.py migrate`, and `python scripts/dev.py api-smoke` pass.
- Authenticated browser checks pass for Review Desk, Incidents, Opportunity-to-detail navigation, Sources and Health, and mobile list/detail return.
- The anti-vibe scanner reports no unintended high or medium findings; any intentional exception is documented inline.

## Plan self-audit

- Access to information: the plan removes unbounded lists, keeps filters and list position, exposes detail immediately, and gives Opportunities decision columns rather than decorative summaries.
- Governance: the plan keeps every evidence and authorization boundary and makes mutations more explicit.
- Scope: no source acquisition, scoring-policy, learned-model, outreach, or production-deployment expansion is included.
- Technical fit: the existing APIs already support offset/limit pagination. The redesign can bound rendered rows without a database migration; new server filters are not required for this pass.
- Reversibility: changes remain in the web application and documentation. No historical migration, score, match, retrieval, or audit record is deleted.
- Verification: the plan includes the repository's mandatory commands plus rendered interaction checks at the exact mobile size that exposed the current failure.
