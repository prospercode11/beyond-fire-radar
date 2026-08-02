# Phase 4 — Property ingestion and entity resolution

Status: complete — accepted for the local/manual prototype gate; official property-source approval remains open

## Scope and boundaries

Implement the Sarasota property-data foundation using approved manual/file imports and realistic local fixtures. The import path supports official bulk-file shapes without activating live property polling or claiming that a source license or approval exists. Synthetic fixtures are test evidence only. Phase 4 does not score opportunities, send notifications, contact consumers, or build the final dashboard.

## Concrete checklist

- [x] Add migration-owned property import, raw-row, mapping-profile, parcel, address-alias, building, and provenance models.
- [x] Add CSV, XLSX, and ZIP import adapters with manual mappings, saved profiles, previews, schema validation, duplicate detection, partial-failure reporting, and immutable raw values.
- [x] Support full and incremental imports, updates, removals, repeat replay, rollback-safe transactions, and audited rollback.
- [x] Normalize exact addresses, units, directional/street variants, blocks, intersections, highways, landmarks, and malformed/incomplete dispatch locations while retaining originals.
- [x] Generate multiple parcel candidates with deterministic and explainable weighted evidence, score margins, contradictions, data-quality limitations, and explicit exact/strong/ambiguous/weak/unresolved outcomes.
- [x] Abstain for low-precision locations, close candidates, unit ambiguity, missing/stale property data, invalid geometry, or contradictory evidence.
- [x] Add authenticated candidate/review APIs and preserve human confirmation, correction, rejection, and clearing across reprocessing.
- [x] Add realistic synthetic fixtures and adversarial tests for imports, addresses, candidates, abstention, rollback, reprocessing, and provenance; SQLite uniqueness/provider-lock boundaries are documented.
- [x] Run the repository verification contract, migration checks, API smoke, and isolated application/API verification. Browser inspection is deferred to Phase 6 because this phase exposes authenticated APIs, not the final dashboard.
- [x] Run independent Luna data-quality reviews; fix all critical/high findings; update execution documents and the Phase 4 handoff.

## Acceptance gate

The Phase 4 local/manual gate passes: executable evaluation cases select the fixture parcel when evidence permits, ambiguous/unit/intersection cases abstain or preserve uncertainty, source-row-to-property provenance is inspectable through the authenticated API, human decisions survive reprocessing, and no exact marker is exposed for block/intersection-only incidents. Real approved property data, PostgreSQL/PostGIS/Redis execution, and production spatial accuracy remain external evidence gates; local fixtures cannot close them.
