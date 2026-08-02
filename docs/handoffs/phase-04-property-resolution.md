# Phase 4 handoff — property ingestion and resolution

Date: 2026-08-01
Status: complete for the local/manual prototype gate; do not treat this as approval for automated official-source retrieval
Commit: `64ac3fd` (`Complete Phase 4 property resolution`)

## Delivered

- Added migration `0007_property_resolution` for provider-scoped property imports, immutable source rows, mapping profiles, parcels, aliases, buildings, field-level provenance, match runs/candidates/features, and human decisions.
- Added manual/file CSV, XLSX, and ZIP import parsing with previews, explicit mappings, mixed-header handling, schema and row errors, duplicate detection, source hashes, full/incremental modes, replay protection, removals, and audited rollback.
- Added versioned address normalization for exact addresses, units, directional/street variants, blocks, intersections, highways/routes, landmarks, malformed locations, municipalities, and ZIP codes while retaining original text.
- Added deterministic/explainable candidate generation using exact/alias/street/house/location/geographic/grid/context/master-unit evidence and explicit score, margin, contradictions, quality, abstention, and human-review states.
- Added authenticated endpoints for mapping profiles, previews/imports/errors/rollback, parcel details with raw-source/field/alias/building provenance, match/reprocess, and confirm/reject/clear/correct decisions.
- Preserved the source approval boundary: the official Sarasota property provider is disabled for automated retrieval and requires an explicit authorized-snapshot attestation; the repository fixture is synthetic and separately labeled.

## Key files

- `apps/api/migrations/versions/0007_property_resolution.py`
- `apps/api/app/properties/address.py`
- `apps/api/app/properties/importers.py`
- `apps/api/app/properties/service.py`
- `apps/api/app/properties/resolution.py`
- `apps/api/app/api/routes/properties.py`
- `apps/api/app/models.py`
- `apps/api/tests/test_property_resolution.py`
- `apps/api/fixtures/sample_sarasota_property_appraiser.csv`

## Verification run

From the repository root:

```text
./scripts/verify.sh                         PASS
python scripts/dev.py migrate               PASS
python scripts/dev.py api-smoke              PASS
```

Additional Phase 4 evidence:

- Focused property suite: `5 passed`.
- Fresh SQLite migration: upgrade to head, downgrade to `0006_scope_incident_aliases_by_provider`, upgrade to head: passed; all Phase 4 tables were present.
- Isolated API: `/healthz` reported `phase: 4-property-resolution` and `live_polling_enabled: false`; `/readyz` was ready.
- Synthetic Sarasota property fixture imported 8 rows, replayed idempotently, produced an exact-address match for `PARCEL-EX100`, abstained for the ambiguous multiunit address, and preserved a confirmed decision after reprocessing.
- Full replacement marked removed parcels inactive; rollback restored parcel projection, source-row provenance, aliases, and building projection from explicit import lineage.
- Mixed-header ZIP, XLSX cell alignment, unit/block/highway normalization, malformed/rejected rows, and provenance inspection were covered by focused tests/reproduction checks.

## External/environment limitations

- No approved real Sarasota property dataset or source-terms evidence was supplied. Synthetic fixture behavior is pipeline evidence only, not accuracy evidence.
- Live Sarasota dispatch polling remains disabled. No Boca, Broadcastify, GIS, permit, outreach, dashboard, or learned-scoring integration was started.
- PostgreSQL/PostGIS and Redis could not be executed because Docker/Colima was unavailable. Spatial production behavior and database-native concurrent import locking require later environment verification.

## Next phase

Phase 5 — transparent opportunity-scoring foundation. Keep property identity resolution separate from ranking; do not infer insurance coverage, claim validity, or consumer contact eligibility.
