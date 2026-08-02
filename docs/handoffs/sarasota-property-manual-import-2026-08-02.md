# Sarasota manual property import handoff — 2026-08-02

## Result

The official Sarasota parcel/sales CSV, detailed property data, and parcel GIS geometry were downloaded and imported into the local SQLite application database as one audited manual snapshot.

- Provider: `sarasota.property_appraiser`
- Source version: `sarasota.scpa.2026-08-02`
- Property import ID: `64e7e421-518b-4ea1-97c5-f3d8701884f0`
- Import status: `imported_with_rejections`
- Acquisition mode: `manual_snapshot`
- Authorization basis: `manual_attestation`
- Normalized import hash: `8b4a3490636c493028df57b231581f9c50880244d20ee923fd73207d0bb9691e`
- Accepted parcels/source rows: `324,924`
- Parcel geometries: `250,986` WGS84 Polygon/MultiPolygon objects
- Rejected rows: `6`, all `missing_required_value` for address
- Materialized detailed field values: `4,159,440`
- Raw payload reference: `local://sarasota.property_appraiser/8b4a3490636c493028df57b231581f9c50880244d20ee923fd73207d0bb9691e`

## Source artifacts

- Official download page: [Sarasota County Property Appraiser data downloads](https://www.sarasotapropertyappraiser.gov/downloads/download-data/)
- Parcel/sales archive: `SCPA_Parcels_Sales_CSV.zip`; SHA-256 `e7c625aaacd20ab4709da7abfefa54bdff093cc3f59e993d7e0309434b0c1da1`
- Detailed archive: `SCPA_Detailed_Data.zip`; SHA-256 `6feec5a57a65b119c21918bfb0a888f4a7dd990a0c4fe104e1834f823e7d5a49`
- GIS layer: [Sarasota parcel ArcGIS layer](https://services3.arcgis.com/icrWMv7eBkctFu1f/arcgis/rest/services/ParcelHosted/FeatureServer/0)
- Captured GIS layer note: `ParcelHosted/0 last edit 2026-08-01T01:05:34Z`
- Durable raw source ZIPs: `data/raw-snapshots/sarasota.property_appraiser/source-downloads/2026-08-02/`

## Verification

- Streaming importer replay returned `replayed=true` with the same import ID and content hash.
- Database counts: 324,924 active parcels, 324,924 immutable source rows, 324,924 building projections, 634,912 aliases, and 4,159,440 detailed field values.
- Geometry reconciliation: 250,986 JSON Polygon/MultiPolygon values and 73,938 explicit JSON null geometry values.
- Source provenance: one parcel/sales hash pair and one GIS service/layer pair across all accepted source rows.
- API `/healthz`: `status=ok`, live Sarasota dispatch polling enabled, worker enabled, interval `900` seconds.
- API property retrieval: authenticated parcel `0000007005` returned the current import, source row, raw payload reference, aliases, building, and field provenance.
- `./scripts/verify.sh`: passed — Ruff, mypy, 62 tests, web lint, and production Next build.
- `./.venv/bin/python scripts/dev.py migrate`: passed — database at migration head.
- `./.venv/bin/python scripts/dev.py api-smoke`: passed.

## Boundary and limitations

The official property provider remains disabled for automated retrieval. The manual attestation records operator-supplied file handling only; it is not legal approval, source-license/terms evidence, production authorization, or a property-match/spatial-accuracy claim. Live Sarasota dispatch polling remains a separate guarded control at the existing 15-minute interval. No Boca, Broadcastify, property polling, consumer outreach, or additional external integration was added.
