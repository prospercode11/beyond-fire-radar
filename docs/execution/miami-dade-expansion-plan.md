# Miami-Dade expansion plan

Status: public GIS import complete; Property Appraiser bulk CSVs pending authorized access

## Goal

Make Beyond Fire Radar a multi-jurisdiction workflow that can ingest and display
Sarasota County and Miami-Dade County fire-call sources, preserve the public
source's uncertainty, and resolve eligible properties through a Miami-Dade
property provider without pretending that an inaccessible bulk file was
downloaded.

## Verified source posture

| Source | Intended use | Access posture | Important limitation |
| --- | --- | --- | --- |
| [Miami-Dade Fire Rescue active calls](https://www.miamidade.gov/firecalls/calls.html) | Active dispatch ingestion | Public HTML page | The page is an automatically refreshed active-call display, not a complete incident archive. RCVD is approximate, addresses can be blocks/cross-streets or general references, and the agency says initial incident information can change without the page depicting every change. |
| [Miami-Dade parcel GIS layer](https://gisweb.miamidade.gov/arcgis/rest/services/Wasd/GovBound_8_v1/MapServer/0) | Public parcel attributes and polygon geometry | Public ArcGIS REST feature layer | Querying is bounded by the service's record limit and must be chunked. It is not the Property Appraiser's sales-history bulk file. |
| [Miami-Dade GIS data service](https://www.miamidade.gov/global/service.page?Mduid_service=ser1468850841882434) | Official GIS/open-data provenance | Public county service documentation | The county identifies parcel layers as primary GIS data and points users to its Open Data Hub for downloads. |
| [Miami-Dade Property Appraiser bulk library](https://bbs.miamidade.gov/) | Parcel, sales, and building-detail CSVs | Account/credits required | The official library states that files are weekly CSVs and cost 50 credits / $50 per file. The implementation will accept supplied authorized files, but will not bypass login, payment, or certificate controls. |

## Implementation sequence

1. Add a jurisdiction-neutral provider contract while retaining the existing
   Sarasota provider and historical provenance.
2. Add `miami_dade.fire_calls` with a parser for the MDFR table columns (`RCVD`,
   `FC`, `INC TYPE`, `ADDRESS`, `UNITS`). Store the original row and source URL,
   map `RCVD` to an approximate event time, and mark the location precision as
   approximate unless the source provides a usable coordinate.
3. Add `miami_dade.property_appraiser` as an authorized file-import provider,
   plus a public GIS parcel download script. The script records the URL, query
   parameters, retrieval timestamp, content hash, record count, and geometry
   format. The public GIS snapshot is now imported locally; it must not claim
   that paid sales/building CSVs are present.
4. Make the dashboard copy, provider selectors, source posture, and incident
   detail labels derive from provider metadata instead of saying Sarasota.
5. Add a deterministic Beyond Adjusting fit proximity component. The component
   uses a configurable public Boca Raton geographic anchor, not a private home
   address or a claim about a person's residence. Distance contributes 20% of
   the fit component, decreases continuously with distance over a documented
   Florida service radius, and is omitted (with an explicit evidence note) when
   parcel coordinates are unavailable.
6. Reprocess only after the scoring version and provider migrations are in
   place. Preserve prior score versions and audit the current one.

## Acceptance gates

- A Miami-Dade HTML snapshot parses into normalized rows with preserved `FC`,
  `UNITS`, original address, approximate-time/location notes, and source URL.
- Replaying the same snapshot is idempotent and does not create duplicate
  incidents or evidence groups.
- A Miami-Dade parcel geometry response can be downloaded in bounded chunks and
  is stored as raw, reproducible input. Paid bulk CSV import is tested with a
  supplied authorized fixture/file only; no synthetic record is used as real
  evidence.
- The dashboard renders “Multi-county” or the selected jurisdiction and shows
  the provider/source that produced each record.
- Fit evidence shows anchor, distance, weight, and proximity factor. No private
  residence data is stored or inferred.
- `./scripts/verify.sh`, `./.venv/bin/python scripts/dev.py migrate`, and
  `./.venv/bin/python scripts/dev.py api-smoke` pass. External PostGIS/Redis
  gates remain explicitly reported when unavailable.

## Known boundary

The public GIS layer can provide parcel attributes and geometry, but it does not
substitute for the Property Appraiser's paid weekly parcel/sales/building CSVs.
Those exact CSVs will become importable and provenance-tracked once an
authorized account/file is supplied. Until then, the app must label the
property source as public GIS or operator-supplied data rather than implying
that sales history or detailed building data is complete.
