# Data dictionary

## Phase 1 through Phase 10 tables

Phase 6 adds no database tables or source fields. The dashboard reads governed APIs and must not create inferred records, map points, property candidates, or score facts in the browser. Phases 7 and 8 add internal workflow/outcome tables; these are not external-source evidence and do not enable consumer outreach.

| Table | Purpose | Provenance/audit rule |
| --- | --- | --- |
| `users` | Internal identities | Password hashes only; no plaintext credential storage |
| `roles` / `user_roles` | Server-side RBAC | Role changes must be audited when provisioning is added |
| `sessions` | Expiring database-backed bearer sessions | Store token hash, never raw token; expiry, idle use, revocation, and replacement timestamps are server-managed |
| `audit_events` | Immutable security/workflow event record | Actor, action, resource, request ID, metadata, timestamp, sequence, previous hash, and event hash; chain verification is required |
| `audit_chain_heads` | Current tamper-evident audit-chain head | Single chain sequence/hash updated with each event; mismatch blocks trust in the audit stream |
| `providers` | Provider contract and authority metadata | Limitations and authorized-use status are explicit |
| `provider_retrievals` | One snapshot retrieval/import attempt | Hash, parser/schema versions, counts, failure/circuit state, retrieval/effective time, acquisition mode, authorization basis |
| `raw_snapshots` | Content-addressed raw payload reference | Provider/content-hash/acquisition-mode scoped replay identity; never overwrite; retention may mark `payload_purge_pending_at` before deletion and tombstone bytes with `payload_purged_at` while retaining provenance |
| `provider_health` | Current operational health summary | Last status, failure count, circuit state, and schema-alert count |
| `provider_poll_leases` | Database-backed Sarasota scheduler lease and latest cycle state | One provider-scoped lease prevents overlapping workers; owner, expiry, start/finish, status, and bounded error are retained |
| `import_jobs` | Idempotent manual/import job envelope | Provider-scoped key, request hash, retrieval reference, and creator |
| `parser_versions` | Registered parser/schema contract | Provider, active version, expected fields, required fields |
| `schema_alerts` | Persisted schema drift and zero-row alerts | Retrieval, severity, observed/missing/unexpected fields, message |
| `raw_dispatch_rows` | Row-level source preservation | Snapshot, row number, source record ID, row hash, raw row payload |
| `dispatch_observations` | Phase 2 normalized dispatch observations | Source IDs, original wording/location, taxonomy/parser versions, confidence, raw reference |
| `import_errors` | Row/parser failure visibility | Job, row, stable code, message, optional raw row payload |
| `canonical_incidents` | Canonical Sarasota incident ledger | Versioned classification, state, confidence/review bands, aggregate times/location, contradiction count, active/merge lineage, explanation |
| `incident_observation_links` | Current and historical incident-to-source-observation assignments | Raw row and observation IDs, link method, creation/end timestamps, current marker, decision actor; old assignments remain inspectable after merge/split and can be selected at an as-of boundary |
| `incident_aliases` | Source identifiers observed for an incident | Source record/event/case values, collision flag, observation provenance |
| `incident_match_decisions` | Immutable deterministic/probabilistic/manual linkage decisions | Candidate/reference IDs, stage, score, feature values, thresholds, explanation, linkage version, actor/time |
| `incident_evidence` | Supporting and contradictory evidence | Incident, immutable observation, evidence type/code, summary, source details, timestamp |
| `incident_timeline_events` | Incident lifecycle and state timeline | Event type, time, prior/new state, source observation, details, actor |
| `incident_merges` / `incident_splits` | Audited manual correction operations | Survivor/absorbed or original/new IDs, moved observations, reason, explanation, actor/time |
| `incident_processing_runs` | Retrieval-scoped incremental/rescore processing envelope | Acquisition mode, linkage/classification versions, counts, status, actor/time; unique retrieval replay guard |
| `responding_agencies` / `responding_stations` | Incident-level responder evidence derived from source observations | Incident, immutable observation, source agency/station, observed time; unique per source observation |
| `incident_dispositions` | Reserved disposition evidence relationship for manual/source-supported disposition records | Incident, optional source observation, source text, disposition, timestamp, reviewer identity; no disposition is inferred in Phase 3 |
| `property_mapping_profiles` | Reusable provider-specific manual field mappings | Provider, named mapping, version, creator, timestamps; changes are not implicit |
| `property_imports` | Versioned CSV/XLSX/ZIP property import envelope | Provider-scoped idempotency/content hash, source/parser/schema versions, acquisition/authorization, effective/retrieved times, raw payload reference, counts, current lineage, rollback status, and failure-safe `payload_purge_pending_at`/`payload_purged_at` retention state |
| `property_import_errors` | Property parser/schema/row failure visibility | Import, row, stable code/message, raw row payload |
| `property_source_rows` | Immutable property source-row preservation | Import, file, row number/hash, raw payload, source parcel ID, normalized fields, acceptance/error status |
| `parcels` | Current provider-scoped parcel projection | Current import/source-row links, original/normalized address components, property fields, active/removal status, data quality |
| `parcel_address_aliases` | Current derived situs/alternate address projections | Parcel, import provenance, original and normalized alias/type; rebuilt for full replacement and rollback |
| `property_buildings` | Current parcel/building/unit projection | Parcel, import provenance, building key, unit/stories/area; rebuilt for full replacement and rollback |
| `property_field_values` | Field-level source-to-normalized provenance | Import, parcel, immutable source row, raw/normalized values, transformation/version, availability/retrieval times |
| `incident_property_match_runs` | Versioned incident-to-property resolution execution | Incident, provider/import, matcher/address versions, source observations, candidate count, status/abstention, actor/time |
| `incident_property_candidates` | Ranked parcel candidates and explanations | Incident/run/parcel, score/margin/classification/recommendation, supporting/contradictory evidence, features, quality |
| `property_match_features` | Reproducible candidate feature values | Candidate, feature/version, numeric/text value, contribution, availability, explanation |
| `property_match_decisions` | Immutable human property-resolution decisions | Incident/candidate/parcel/run, confirm/reject/clear/correct, reason, actor/time |
| `scoring_versions` | Immutable registry of active/retired scoring releases | Component versions, non-probability priors/rules, description, creator, and creation time; releases must be reproducible and selectable by version |
| `opportunity_score_runs` | Versioned incident ranking executions | Incident/property-run/provider, scoring version, as-of boundary, explicit predecessor, provisional score/tier, hard gate/abstention, alert eligibility, explanation, source observations, current marker, and audit timestamps |
| `opportunity_score_features` | Feature-level score evidence and contribution record | Score run, value/status, log-space contribution, source observations, availability, feature version, evidence, and explanation; missing values remain visible |
| `opportunity_score_overrides` | Immutable reviewer decisions over score presentation/eligibility | Incident/score run, suppress/promote-review/hold/clear decision, reason, reviewer, timestamp; baseline score runs are not rewritten |
| `internal_alerts` | Deduplicated internal review alerts | Incident/score run, stable dedupe key, eligibility evidence snapshot, status/suppression/revocation/acknowledgment timestamps, and actor fields; no consumer delivery fields |
| `notification_jobs` | In-app notification delivery jobs | Alert/channel unique key, status, attempts, error, and timestamps; only `in_app` is enabled and all dispatches are audited |
| `incident_assignments` | Current and historical internal incident ownership | Incident, assignee, role, reason, actor, start/end timestamps; current assignment is unique and changes are audited |
| `workflow_notes` | Append-only internal incident review notes | Incident, note body/type, author, and timestamp; edits/deletes are not exposed |
| `client_imports` | Internal existing-client roster import envelope | Idempotency/content hash, raw payload reference, counts, creator, and timestamp; manually supplied internal data only |
| `existing_client_records` | Immutable row-level internal client reference data | Import/row, client key, normalized address/parcel, do-not-contact flag, source note, raw row, and timestamp |
| `outcome_labels` | Append-only reviewer labels for relevance, classification, property match, alert usefulness, and client status | Incident/optional score run, optional reviewed alert, property prediction/match/candidate/decision bindings where applicable, versioned label type/value, approved error category, rationale, manual provenance, explicit idempotency key, reviewer, and timestamp; labels are not source approval or legal conclusions |
| `incident_outcome_events` | Append-only internal funnel/outcome events | Incident/optional score run, controlled event type, occurred/created times, manual source, details/provenance, idempotency key, actor, and audit event; no outreach is inferred |
| `evaluation_manifests` | Reproducible as-of input set for an analytics report | Immutable incident, score-run, label, outcome-event, dispatch retrieval, property import, acquisition-mode, provider, authorization, snapshot/content hash, filter, claim-status, creator, and timestamp references |
| `analytics_metrics` | Persisted metric outputs for one evaluation manifest | Versioned metric name, numerator/denominator/value/status, warning, calculation details, manifest, and timestamp; prior reports are not overwritten |
| `learning_feature_sets` | Versioned feature contract for reproducible training rows | Feature names, definitions, missing-value semantics, creator, and timestamp; feature versions are immutable |
| `learning_label_sets` | Versioned label contract for supervised outcomes | Label type, permitted positive/negative/excluded values, definition, creator, and timestamp; labels remain manual/internal outcomes |
| `training_dataset_snapshots` | Immutable manifest-bound training dataset and split snapshot | Feature/label versions, as-of/filter/provenance references, serialized rows, incident-grouped chronological assignments, leakage report, eligibility, blocked reasons, and idempotency key |
| `model_releases` | Versioned blocked/inactive/candidate/challenger/champion/retired/rollback model registry | Algorithm, feature/label/dataset lineage, artifact, evaluation, training report, model card, approval/deployment fields, predecessor, inactive reason, creator, and timestamp; migration `0018` constrains allowed states and enforces one champion |
| `model_replay_runs` | Frozen offline replay of a model release | Model/dataset references, metrics, explicit accuracy-claim boundary, idempotency key, actor, and timestamp |
| `model_drift_reports` | Feature-distribution drift comparison between dataset snapshots | Feature contract, baseline/comparison snapshots, threshold, per-feature metrics/status, explicit non-accuracy boundary, idempotency key, actor, and timestamp |
| `model_control_actions` | Idempotent administrator promotion/rollback intent and result | Unique idempotency key, action, target/result release IDs, actor, action metadata, and timestamp; release state remains database-guarded |
| `feature_flags` | Controlled activation boundary | Legally gated or incomplete integrations default off |
| `legal_approvals` | Approval evidence | Approval status and notes retained |

## Future field rules

Every normalized external field must retain provider, raw record ID, raw field name/value, normalized value, transformation/version, confidence, effective time, and retrieval time. Every model feature must carry an `available_at` timestamp and feature version. Every score run must carry an `as_of` boundary and explicit scoring release. Every manual label must carry reviewer identity, timestamp, reason, and source evidence where applicable.

Phase 5 scoring is a versioned expert-prior evidence ranking only. `provisional_score` is not a probability, and alert eligibility is a hard-gated review state. No score field is evidence of damage, coverage, claim validity, or consumer contact eligibility.

Phase 3 linkage is an explainable weighted baseline, not machine learning. A possible match is kept separate pending human review; no fuzzy-only merge is permitted. Incident classification remains source-faithful and does not infer a working fire from an unverified signal.

Phase 6 UI state is not domain evidence. Loading, API-unavailable, empty, freshness, live/manual-source, uncertainty, and human-review labels are presentation states and must remain consistent with the underlying API provenance and authorization posture. The dashboard reads the API health contract for the Sarasota polling flag, worker flag, and exact interval rather than assuming a static status.

Live polling is a separately controlled acquisition mode. Local development may record `authorization_basis=explicit_user_permission` only when the feature flag and worker are enabled; this basis is an operator authorization for the local prototype, not a legal approval. Production/staging require a persisted approved `LegalApproval`. Every live retrieval and processing run retains `live_poll`, provider, raw snapshot, content hash, parser/schema versions, authorization basis, and audit references.

Phase 8 labels/events are internal manual outcomes, not external source facts. Accuracy and conversion metrics use explicit denominators and warnings; synthetic acquisition modes make reports non-real-world evidence. A manifest fixes the IDs and as-of boundary used by its metric rows. Model Lab readiness is a blocked contract until real held-out labels, leakage checks, calibration, error analysis, and administrator approval are available.

Phase 9 learning artifacts are reproducible mechanics, not evidence that a learned model is accurate. Feature rows are bound to an as-of score run and labels are bound to a later manual outcome boundary; incident groups cannot cross splits. A model release cannot become a champion while real-data eligibility, held-out improvement, calibration, top-alert precision, error analysis, administrator approval, or the serving feature flag is missing. The rule-based fallback remains the only active policy.
