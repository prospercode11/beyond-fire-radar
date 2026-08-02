# Source registry

| Provider ID | Source | Coverage | Data type | Current state | Limitations |
| --- | --- | --- | --- | --- | --- |
| `sarasota.official_dispatch` | [Sarasota County 911 Dispatch Reporting interface](https://dispatchreporting.scgov.net/Events?strAgencyID=All) | Sarasota County, FL | Dispatch snapshot | Manual snapshot processing is enabled for explicitly attested imports; live polling disabled | No CAPTCHA/access-control/rate-limit bypass; `ENABLE_LIVE_SARASOTA_DISPATCH_POLLING=false`; `provider_retrievals.acquisition_mode=manual_snapshot`; no automated live retrieval or invented legal approval |
| `fixture.sarasota.dispatch` | Repository synthetic fixture modeled on the Sarasota dispatch schema | Synthetic Sarasota County shape | Dispatch snapshot | Enabled for tests and local smoke only | Not an external authority; not accuracy evidence |
| `sarasota.property_appraiser` | Sarasota County Property Appraiser bulk datasets | Sarasota County, FL | Property/tax roll bulk file | Manual/file prototype path implemented; automated retrieval disabled | Official source approval/terms evidence is not supplied; imports require explicit authorized-snapshot attestation; versioned mapping/import/provenance/validation are required; synthetic fixtures are not accuracy evidence |
| `fixture.sarasota.property_appraiser` | Repository synthetic fixture modeled on property bulk-file shape | Synthetic Sarasota County shape | Property/tax roll bulk file | Enabled for local tests and manual prototype workflow | Not an external authority; never evidence of property-match accuracy |
| `sarasota.gis` | Sarasota County official GIS/open-data resources | Sarasota County, FL | GIS layers | Not implemented | Requires layer-by-layer source/terms verification |
| `sarasota.permits` | Authorized permit datasets | Sarasota County, FL | Permit records | Not implemented | Manual import first unless authorized integration is confirmed |
| `sarasota.outcomes` | Authorized CAD/fire/public-record/manual outcomes | Sarasota County, FL | Outcome labels | Not implemented | Not assumed real-time; labels require reviewer identity and timestamp |
| `internal.client_roster` | Internal existing-client roster supplied by an authorized user | Internal | Client suppression/reference CSV | Manual/file import enabled for internal workflow only | Not an external authority; rows are retained for provenance and suppression controls; no consumer outreach is implemented |

Every activated provider must populate authority, authorized-use status, enabled state, interval, retrieval/effective times, schema/parser versions, hashes, counts, health, failure state, terms note, and approval/contact note.

Incident processing is provenance-gated by acquisition mode: `manual_snapshot` and `synthetic_fixture` are available for the prototype workflow; `live_poll` is rejected while live polling is disabled. This distinction is retained on retrievals and processing runs and surfaced on incident detail responses.

Phase 5 scoring preserves the same provenance boundary. A score may be computed for research/review from current manual or fixture records, but an operational alert requires only explicitly authorized `manual_snapshot` retrievals with an authorization basis, a resolved property match, no contradiction/negative hard gate, and available fit evidence. Synthetic fixtures and live/unauthorized retrievals cannot satisfy that alert gate; this is an application control, not a legal approval.

Phase 6 adds no external provider. The dashboard reads governed incident/retrieval/property/score APIs, labels Sarasota County manual snapshots, shows live polling as disabled, and presents safe empty states when no approved record is available. Its incident-map surface has no live GIS feed and must not be read as geospatial evidence.

Phase 7 adds only the internal client-roster workflow source. Client CSV rows are manually supplied internal reference data, not external-source approval evidence. Internal alert delivery is in-app only; email, SMS, phone, and consumer outreach channels are disabled and unimplemented.

Phase 8 and Phase 9 add no external provider. Human outcome labels and funnel events are internal manual reviewer records with identity, timestamp, rationale, idempotency, and audit provenance. Evaluation manifests and training snapshots retain the dispatch acquisition modes used by their cases; synthetic fixtures remain pipeline evidence only, and the `sarasota.outcomes` external row remains unimplemented. Learning artifacts cannot convert a manual record into source approval, cannot activate live polling, and cannot support an accuracy claim without real approved held-out evidence and administrator approval.
