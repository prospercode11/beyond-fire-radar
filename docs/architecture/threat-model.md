# Foundation and dispatch-ingestion threat model

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
| Replay/idempotency failure | Provider-scoped idempotency keys, content hashes, and unique raw/normalized row constraints | Concurrent multi-writer behavior and production database testing require the external integration environment |

## Required production follow-up

Before production use, complete identity/MFA, secret management, TLS, rate limiting, dependency scanning, backup/restore, retention, access review, and a security review. This document is a foundation threat model, not a production security approval.
