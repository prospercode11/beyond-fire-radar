# Product specification

## Mission

Beyond Fire Radar is an internal property-loss intelligence system for Beyond Adjusting. Its job is to reduce the time spent finding and triaging authorized fire-related property signals while preserving uncertainty, provenance, and human control.

The primary optimization target is high precision among the first opportunities reviewed by Beyond Adjusting. The system may abstain or route a record to research when evidence is insufficient.

## Terminology

- **Incident:** a canonical fire-service event assembled from source records.
- **Observation:** an individual dispatch row, update, imported disposition, or source record.
- **Property candidate:** a parcel or structure that might correspond to an incident location.
- **Property match:** a candidate selected with a measured confidence or, after calibration, a probability.
- **Opportunity:** an incident-property combination that passes minimum relevance criteria.
- **Licensed Review Priority:** the ranking of opportunities for human review.
- **Empirical Opportunity Probability:** a calibrated probability produced only after sufficient real labeled data exists.

## Non-goals and safety boundary

The system does not state that a property sustained damage, has insurance coverage, has a valid claim, should file a claim, will hire Beyond Adjusting, or has a predicted payment. It does not perform consumer outreach, claim filing, contract generation, or automated recommendations. Any later outreach capability requires separate legal approval, feature flags, human approval, and auditable controls.

## Phase 0 through Phase 3 product slice

The current slice establishes:

1. A repository and documentation contract.
2. A modular-monolith API with migration-owned storage.
3. Secure-enough local bootstrap authentication, database sessions, and role primitives.
4. Immutable audit-event storage for security-sensitive actions.
5. A provider registry capable of representing authorized, disabled, fixture, and not-yet-verified sources.
6. Authorized manual Sarasota dispatch snapshot ingestion with preserved raw evidence, parser/schema versions, replay protection, and visible health/errors.
7. Canonical Sarasota incidents with conservative deduplication/linkage, versioned classification, timelines, state transitions, contradiction evidence, provenance explanations, and audited merge/split controls.
8. A runnable web shell that does not imply an operational dashboard.

Property resolution, address-to-parcel matching, scoring, dashboard, notifications, Boca/Broadcastify, and outreach remain outside the current slice.

## Future user outcomes

An authorized reviewer will eventually be able to inspect raw observations, canonical incidents, property candidates, evidence, uncertainty, source freshness, model versions, assignments, suppressions, and manually recorded outcomes. Every external fact will retain provenance and every automated decision will be reversible and auditable.
