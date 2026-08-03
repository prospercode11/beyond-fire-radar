# Phase 4 — Property ingestion and entity resolution

Status: complete — accepted for the local/manual prototype gate; official property-source approval remains open
Updated: 2026-08-03 after property issue-fix verification

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

## 2026-08-02 manual Sarasota snapshot

An operator-supplied snapshot from the official Sarasota Property Appraiser download listings was imported through the bounded, audited file workflow’s streaming normalized-CSV command. The parcel/sales ZIP, detailed ZIP, normalized import, and official parcel GIS layer are recorded with hashes and row-level provenance in `docs/data/source-registry.md` and `docs/handoffs/sarasota-property-manual-import-2026-08-02.md`. The import is labeled `manual_snapshot` with `manual_attestation`; it does not create legal approval, source-terms evidence, automated property polling, or a real-world accuracy claim.

## 2026-08-03 issue-fix verification

The authenticated workbench now lists the current snapshot and explicitly matches it before rescoring. The property panel displays source version, accepted-row count, acquisition mode, authorization basis, and content-hash prefix. Matching normalizes database-naive effective timestamps as UTC and accepts the components both sides supplied, so `11704 ALTAMONTE CT` matches the current Sarasota parcel snapshot without treating the street number as a postal code. A historical import ID is rejected for new matching unless it is the current provider projection; this prevents a historical provenance label from being paired with current parcel data. Upload/import, match, and rescore errors are visible to the operator. The score remains a versioned review-only ranking when fit evidence is absent.
