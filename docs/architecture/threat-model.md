# Foundation, dispatch-ingestion, and property-resolution threat model

## Assets

- Internal user identities and session material.
- Owner/organization research that will be introduced in later phases.
- Raw source records and provenance.
- Reviewer decisions, suppressions, assignments, labels, and audit events.
- Model artifacts and configuration.

## Threats and controls

| Threat | Phase 1/2 control | Residual risk |
| --- | --- | --- |
| Unauthenticated access | Bearer sessions, password verification, protected routes | Production identity provider, MFA, rate limiting, and session rotation are later hardening work |
| Privilege escalation | Server-side role dependency and administrator-only provider disable/audit routes | User provisioning and complete authorization matrix are future work |
| Token leakage | Only token hash is stored; bearer token is returned once | HTTPS, secure browser storage, rotation, and revocation endpoint hardening require production review |
| Source misuse | Provider authorization status, disabled live provider, manual-upload attestation, explicit limitations | Written source approvals and terms are not yet present; no approved snapshot is stored |
| Data tampering | Migrations, content-addressed immutable snapshot store, raw row preservation, audit records | Database/operator access and retention controls require production hardening |
| False model claims | No probabilities or accuracy claims; source wording and unknown taxonomy are preserved | Future models require real held-out labels and calibration gates |
| Unauthorized outreach | No outreach routes, jobs, or sender integration | Future work must remain feature-flagged and legally approved |
| Replay/idempotency failure | Provider-scoped idempotency keys, content hashes, unique raw/normalized row constraints, and unique retrieval processing runs | Concurrent multi-writer behavior and production database testing require the external integration environment |
| Transitive incident over-merge | Conservative deterministic guards, explainable multi-feature baseline, cluster time/location/identifier limits, human-review band, and adversarial tests | Real-world address quality and provider identifier reuse still require reviewer oversight |
| Contradictory source evidence hidden | Raw rows and observations remain immutable; contradictory evidence, collision aliases, timelines, and original linkage decisions are retained | Resolution/disposition workflows are future human-review work |
| Unauthorized live-source processing | Acquisition mode is persisted; incident processing accepts manual/fixture modes and rejects live-collected mode while the feature flag is disabled | Written source approval and production integration evidence remain separately tracked |
| Property source misuse | Official property provider is disabled for automated retrieval; file imports require explicit attestation; synthetic fixtures carry separate provenance | Written source approval/terms and an approved real snapshot are not present |
| Wrong parcel or overconfident match | Versioned normalization, multiple candidate evidence, score/margin, contradictions, source quality, unit/master protections, abstention, and human decisions | Real property accuracy and spatial database behavior require approved data and production evaluation |
| Stale derived property projection | Full imports rebuild aliases/buildings; rollback follows explicit import lineage; immutable property source rows remain available | Database-native concurrency and operational restore testing require PostgreSQL/integration environment |

## Required production follow-up

Before production use, complete identity/MFA, secret management, TLS, rate limiting, dependency scanning, backup/restore, retention, access review, and a security review. This document is a foundation threat model, not a production security approval.
