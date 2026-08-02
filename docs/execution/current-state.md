# Current state

Updated: 2026-08-01 after Phase 8 verification
Scope: Phase 0 through Phase 8 only

## Implemented

- Repository policy in `AGENTS.md`.
- Architecture/product/modeling/compliance/data/testing documents.
- FastAPI API under `apps/api`.
- SQLAlchemy models and migration-owned schema through `0006_scope_incident_aliases_by_provider`.
- SQLite local mode; PostgreSQL/PostGIS and Redis service definition.
- One-time configured admin bootstrap, password verification, expiring bearer sessions, and server-side role checks.
- Provider registry for a synthetic fixture and a fail-closed Sarasota live provider.
- Authorized manual Sarasota dispatch snapshot ingestion for CSV, HTML, and JSON.
- Immutable content-addressed raw snapshot storage, raw dispatch rows, normalized observations, and audit events.
- Versioned parser/schema metadata, source-faithful taxonomy, parser comparison, schema alerts, import errors, replay protection, and provider health.
- Next.js web shell under `apps/web`.
- Unit/integration/API smoke verification scripts.
- Canonical Sarasota incident assembly with deterministic identifiers, conservative explainable probabilistic linkage, confidence/review bands, and anti-transitive-overmerge checks.
- Versioned incident classification, incident timelines, guarded incident state transitions, incremental processing, and explicit rescore hooks.
- Contradictory-evidence preservation, immutable raw/source-row relationships, provenance-bearing incident detail, and explanations for matches and kept-separate candidates.
- Audited manual incident merge and split controls with source-row preservation.
- Phase 3 migrations `0004_incident_intelligence` through `0006_scope_incident_aliases_by_provider`, API routes, adversarial tests, replay verification, independent review, and handoff.
- Independent reviews and handoffs in `docs/reviews/phase-01-foundation-review.md`, `docs/reviews/phase-02-dispatch-ingestion-review.md`, `docs/handoffs/phase-01-foundation.md`, `docs/handoffs/phase-02-dispatch-ingestion.md`, and the Phase 3 review/handoff produced for this commit.
- Phase 4 migration `0007_property_resolution` with provider-scoped property imports, immutable source rows, mapping profiles, current parcel/building/address projections, field-level provenance, and rollback lineage.
- Manual/file property ingestion for CSV, XLSX, and ZIP, including preview, mappings, schema/row errors, duplicate detection, full/incremental modes, idempotent replay, full replacement/removals, and audited rollback.
- Versioned address normalization for exact addresses, units, directional/street variants, blocks, intersections, highways/routes, landmarks, and malformed locations; original values remain available.
- Explainable parcel candidate generation using normalized addresses, aliases, street/house, municipality/ZIP, coordinates, grid/context, and master/unit relationships with explicit score/margin, contradictions, quality, abstention, and human-review evidence.
- Authenticated property import, parcel provenance, match/reprocess, and human confirm/reject/clear/correct APIs; human decisions remain visible after reprocessing.
- Phase 4 focused adversarial tests, migration round-trip, isolated application/API verification, independent Luna review, and corrected high-severity findings.
- Phase 5 migrations `0009_opportunity_scoring` through `0011_temporal_incident_links` add a versioned scoring registry, score history, feature-level contributions/provenance, human overrides, explicit as-of boundaries, rollback predecessors, and effective-end timestamps for historical incident assignments.
- Transparent opportunity scoring uses separately versioned evidence components, a weighted geometric provisional rank, hard negative/contradiction/property gates, missing-data penalties, human-review bands, and explicit abstention. It is not a probability and does not infer damage, coverage, claim validity, or outreach eligibility.
- Authenticated score/list/rescore/override/version-registration/rollback APIs and leakage-controlled evaluation contracts are implemented. Synthetic and unauthorized/live retrievals cannot produce operational alerts; Sarasota live polling remains disabled.
- Phase 5 focused scoring/evaluation tests, migration round-trip, verification contract, application/API checks, independent Luna review, and corrected high-severity findings are recorded in the Phase 5 review/handoff.
- Phase 6 internal dashboard foundation provides Command Center, Incident Stream, Opportunities, Data Health, Settings, source posture, review queue, incident map, evidence workbench, and property-context surfaces.
- Phase 6 browser states distinguish loading, API-unavailable, and empty data; manual Sarasota provenance, freshness limits, uncertainty, human-review requirements, and disabled live polling remain visible.
- Phase 6 responsive navigation and keyboard-accessible controls were inspected at desktop and 390×844 mobile dimensions; the dashboard has no horizontal overflow and does not fabricate records, map points, property candidates, or scores.
- Phase 6 verification, handoff, and independent Luna review are recorded in the Phase 6 execution/review/handoff documents.
- Phase 7 migrations `0012_internal_workflow` and `0013_workflow_state_guards` add internal alerts, in-app notification jobs, terminal-safe escalation, assignment history, append-only notes, and internal existing-client CSV import rows with idempotency, provenance, suppression, and audit controls.
- Phase 7 workflow APIs provide deduplicated alert generation, suppression precedence, acknowledgment/snooze/resolve/revoke/escalation controls, eligibility-checked unsuppress, in-app-only notification dispatch, incident assignment, notes, and client-roster import. Fixture and unauthorized/live score evidence cannot create operational alerts.
- Phase 7 focused workflow tests, fresh migration/API smoke verification, and the independent Luna review are recorded in the Phase 7 execution/review/handoff documents.
- Phase 8 migrations `0014_outcomes_analytics` through `0016_outcome_alert_provenance` add append-only internal outcome labels/events, reviewed-prediction and alert bindings, dispatch/property source provenance, reproducible evaluation manifests, persisted metric rows, and Model Lab readiness state without training a learned model.
- Phase 8 authenticated APIs enforce label taxonomy, negative-label error categories, explicit idempotent replay, future-event rejection, manifest-bound as-of filters, dispatch/property source provenance, denominators, and small-sample/synthetic warnings. Reports keep technical accuracy separate from conversion and set `accuracy_claim_allowed=false`.
- Phase 8 Outcomes/Analytics workspace view displays saved manifests, dispatch/property source counts, metric denominators/warnings, and blocked Model Lab readiness. No probability, legal approval, damage, coverage, claim-validity, or outreach conclusion is shown.

## Explicitly not implemented

Live Sarasota polling, cross-source deduplication, GIS/permit imports, empirical calibration, learned-model training/deployment, live GIS/map data, production dashboard deployment, email/SMS/phone notifications, and consumer outreach.

## Environment evidence

The host has Docker CLI but its configured Colima daemon is not running, and the Docker Compose plugin is not installed. Therefore the Compose definitions are present but PostgreSQL/PostGIS/Redis integration could not be truthfully claimed as executed in this environment. SQLite migration and application tests are the runnable local path. The parser also accepted a one-time current HTML response from the official Sarasota dispatch page for shape verification; that is not an authorization claim or an activated polling integration.

The external-source approval gate remains intact. Dispatch processing accepts only retrievals explicitly labeled `manual_snapshot` or `synthetic_fixture`; property processing accepts manual/file workflows with an explicit authorization attestation for the official provider and labels synthetic fixture imports separately. No live polling is enabled or implied, no legal approval is invented, and acquisition mode is returned in import, retrieval, processing, incident, parcel, and match evidence. Internal client-roster files are explicitly labeled internal manual reference data and are not approval evidence. The authenticated browser reads through the API and does not bypass source gates. Phase 7 alerts require explicitly authorized manual dispatch evidence, eligible score hard gates, resolved property evidence, and no suppression; in-app delivery is the only enabled channel. PostgreSQL/PostGIS and Redis execution remains unavailable on this host.

## Next controlled step

Phase 9 — learned models — is the next controlled step. Phase 8 is complete only for the internal/local analytics gate; reports remain directional and Model Lab readiness is blocked. Phase 9 must preserve the Phase 8 manifest, label, provenance, leakage, calibration, and approval boundaries. Keep live Sarasota polling, official property automation, production dashboard deployment, empirical model claims, and consumer outreach disabled until their external evidence gates are closed.
