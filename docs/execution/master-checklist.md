# Master checklist

## Phase 0 — Repository audit and architecture

- [x] Repository inventory performed.
- [x] Product specification.
- [x] Architecture decision record.
- [x] System context and data flow.
- [x] Threat model.
- [x] Data model and dictionary.
- [x] Modeling specification.
- [x] Compliance boundaries.
- [x] Source registry.
- [x] Evaluation plan.
- [x] Later-phase task files.
- [x] Phase 0 acceptance gate documented.

## Phase 1 — Foundation

- [x] Monorepo layout.
- [x] Docker Compose definitions for PostgreSQL/PostGIS and Redis.
- [x] Database models and Alembic migration.
- [x] Session authentication and roles.
- [x] Audit framework.
- [x] Provider contract/registry and disabled live provider.
- [x] Synthetic fixture and fixture validation test.
- [x] CI and local verification commands.
- [x] Application/web shell runnable.
- [ ] External PostgreSQL/PostGIS/Redis integration test: blocked by unavailable Docker daemon in this environment.
- [ ] Production identity/MFA and complete user administration: later hardening.
- [x] Phase 1 reviewer findings addressed or documented.
- [x] Phase 1 acceptance gate recorded in handoff.

## Phase 2 — Dispatch ingestion

- [x] Sarasota provider remains fail-closed for live polling.
- [x] Authorized manual snapshot upload boundary with size and attestation checks.
- [x] CSV, HTML, and JSON parser contract with versioned schema metadata.
- [x] Immutable raw snapshot storage and raw-row preservation.
- [x] Source-faithful event taxonomy with explicit unknown/abstain behavior.
- [x] Schema-drift, parser-failure, and zero-row anomaly visibility.
- [x] Provider health, failure state, and schema-alert counters.
- [x] Idempotent replay with no duplicate raw or normalized records.
- [x] Parser comparison and retrieval inspection endpoints.
- [x] Phase 2 contract, migration, API, and replay tests.
- [x] Independent Luna review completed; critical/high findings addressed.
- [ ] Real approved Sarasota snapshot artifact supplied and accepted for the external-source gate.
- [ ] PostgreSQL/PostGIS and Redis integration execution: Docker/Colima unavailable in this environment.

## Phase 5 — Transparent opportunity scoring

- [x] Migration-owned scoring-version registry, score-run history, feature contributions/provenance, human overrides, as-of boundary, temporal incident-link intervals, and explicit predecessor rollback.
- [x] Separately versioned source quality, incident validity, property-match quality, material-loss evidence, loss complexity, Beyond Adjusting fit, freshness, and data-sufficiency components.
- [x] Explainable weighted-geometric provisional ranking with hard negative/contradiction/property gates, missing-data penalties, evidence tiers, and abstention.
- [x] No arbitrary probability, calibration, insurance coverage, claim validity, or consumer-contact inference; synthetic and live/unauthorized sources are ineligible for operational alerts.
- [x] Authenticated score/list/rescore/override/version-registration/rollback APIs with audited human decisions.
- [x] As-of and leakage-controlled evaluation contracts; feature availability and grouped/temporal split tests.
- [x] Adversarial tests cover weak/negative signals, missing property evidence, feature explanations, as-of boundaries, overrides, rescore, rollback, and version registration.
- [x] Independent Luna review completed; critical/high findings addressed.
- [x] Formatting, lint, type, unit, migration round-trip, API smoke, and isolated application/API checks recorded.
- [x] Phase 5 handoff and execution/data/modeling/architecture documents recorded.
- [ ] Real held-out outcomes, calibration, production alert authorization, and PostgreSQL/PostGIS/Redis integration execution remain external gates.
- [x] Phase 2 handoff and acceptance evidence recorded.

## Phase 3 — Incident intelligence

- [x] Phase 3 migration and canonical incident tables preserve source-row relationships and provenance.
- [x] Deterministic deduplication for source record/event/case/address-time evidence.
- [x] Explainable probabilistic linkage baseline with match, human-review, and no-match bands.
- [x] Cluster consistency limits prevent transitive over-merging; reused identifiers remain separate.
- [x] Versioned taxonomy aggregation, contradiction evidence, confidence, and abstention behavior.
- [x] Incident timelines, governed state machine, incremental processing, and rescore hook.
- [x] Audited manual merge and split controls preserve all raw/source rows.
- [x] Match/separation explanations and acquisition-mode provenance are exposed through the API.
- [x] Adversarial tests cover duplicates, missing IDs, conflicting types, reused identifiers, same-address separate fires, malformed rows, replay, and merge/split.
- [x] Independent Luna review completed; critical/high findings addressed.
- [x] Phase 3 formatting, lint, type, unit, migration, API smoke, and relevant end-to-end checks recorded.
- [x] Phase 3 handoff and execution documents recorded.
- [ ] PostgreSQL/PostGIS and Redis integration execution: Docker/Colima unavailable in this environment.

## Phase 4 — Property ingestion and resolution

- [x] Migration-owned property imports, immutable source rows, mapping profiles, parcel/address/building projections, field provenance, and rollback lineage.
- [x] Manual/file CSV, XLSX, and ZIP workflows with previews, mappings, schema/row errors, duplicate detection, replay protection, full/incremental replacement, removals, and audited rollback.
- [x] Versioned normalization for exact/unit/directional/street/block/intersection/highway/landmark/malformed locations while retaining originals.
- [x] Deterministic and explainable candidate generation across address, aliases, street/house, municipality/ZIP, coordinates, grid/context, and master/unit relationships.
- [x] Score, margin, confidence/review bands, contradictions, quality limitations, abstention, no exact marker for low-precision locations, and human decisions through reprocessing.
- [x] Authenticated provenance inspection exposes current import, source row, raw payload, field transformations, aliases, and building projections.
- [x] Adversarial tests cover XLSX/ZIP variations, malformed addresses, units/blocks/highways/intersections, replay, rejected rows, full removal, rollback, provenance, unit ambiguity, and human decisions.
- [x] Independent Luna review completed; all critical/high implementation findings addressed.
- [x] Formatting, lint, type, unit, migration round-trip, API smoke, and isolated application/API checks recorded.
- [ ] Official Sarasota property-source approval/terms evidence and approved real snapshot: external gate remains open.
- [ ] PostgreSQL/PostGIS and Redis integration execution: Docker/Colima unavailable in this environment.

## Phase 6 — Internal review workflow and dashboard

- [x] Responsive internal shell covers Command Center, Incident Stream, Opportunities, Data Health, and Settings.
- [x] Command Center exposes review queue, Sarasota source posture, incident map surface, evidence workbench, and property-context surface.
- [x] Loading, API-unavailable, and empty states are explicit and do not fabricate incidents, map points, property candidates, or scores.
- [x] Manual Sarasota snapshot provenance, freshness limits, uncertainty, human-review requirements, and disabled live polling remain visible.
- [x] Responsive desktop/mobile layout and keyboard-accessible navigation were browser-inspected; mobile has no horizontal overflow.
- [x] No sensational, probabilistic, damage, coverage, claim-validity, or consumer-contact language was introduced.
- [x] Independent Luna review completed; critical/high findings addressed.
- [x] Formatting, lint, type, unit, migration, API smoke, production build, and browser checks recorded in the Phase 6 handoff.
- [x] Phase 6 handoff and execution/review documents recorded.
- [ ] Production dashboard deployment, authenticated data workflows, live GIS, and external PostgreSQL/PostGIS/Redis integration remain later/external gates.

## Phase gate rule

Phase 7 must not start until the Phase 6 handoff is accepted. Live Sarasota polling, official property automation, empirical calibration, outcome capture, notifications, Boca, Broadcastify, outreach, production dashboard deployment, and later phases remain separately gated by their requirements.
