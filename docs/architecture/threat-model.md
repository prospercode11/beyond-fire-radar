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
| Unauthenticated access | Bearer sessions, password verification, protected routes, bounded login rate limits, expiry, idle timeout, active-session cap, revocation/replacement | Production identity provider, MFA, and enterprise provisioning remain external gates |
| Privilege escalation | Server-side role dependency and administrator-only provider disable/audit routes | User provisioning and complete authorization matrix are future work |
| Token leakage | Only token hash is stored; bearer token is returned once; logout/replacement/idle controls and no-store API responses | HTTPS, secure browser storage, secret rotation, and production identity review remain external gates |
| Source misuse | Provider authorization status, disabled live provider, manual-upload attestation, explicit limitations | Written source approvals and terms are not yet present; no approved snapshot is stored |
| Data tampering | Migrations, content-addressed immutable snapshot store, raw row preservation, immutable S3/R2 hash checks, chained audit events, chain integrity endpoint, backups | Database/operator access, managed backup, and staging restore exercise remain external gates |
| False model claims | No probabilities or accuracy claims; source wording and unknown taxonomy are preserved | Future models require real held-out labels and calibration gates |
| Unauthorized outreach | No outreach routes, jobs, or sender integration | Future work must remain feature-flagged and legally approved |
| Replay/idempotency failure | Provider-scoped idempotency keys, content hashes, unique raw/normalized row constraints, and unique retrieval processing runs | Concurrent multi-writer behavior and production database testing require the external integration environment |
| Transitive incident over-merge | Conservative deterministic guards, explainable multi-feature baseline, cluster time/location/identifier limits, human-review band, and adversarial tests | Real-world address quality and provider identifier reuse still require reviewer oversight |
| Contradictory source evidence hidden | Raw rows and observations remain immutable; contradictory evidence, collision aliases, timelines, and original linkage decisions are retained | Resolution/disposition workflows are future human-review work |
| Unauthorized live-source processing | Acquisition mode is persisted; incident processing accepts manual/fixture modes and rejects live-collected mode while the feature flag is disabled | Written source approval and production integration evidence remain separately tracked |
| Property source misuse | Official property provider is disabled for automated retrieval; file imports require explicit attestation; synthetic fixtures carry separate provenance | Written source approval/terms and an approved real snapshot are not present |
| Wrong parcel or overconfident match | Versioned normalization, multiple candidate evidence, score/margin, contradictions, source quality, unit/master protections, abstention, and human decisions | Real property accuracy and spatial database behavior require approved data and production evaluation |
| Stale derived property projection | Full imports rebuild aliases/buildings; rollback follows explicit import lineage; immutable property source rows remain available | Database-native concurrency and operational restore testing require PostgreSQL/integration environment |
| Overconfident or irreproducible opportunity rank | Versioned release registry, as-of boundary, feature/source provenance, hard negative/contradiction/property gates, explicit abstention, human-review bands, append-only overrides, and predecessor rollback | No real outcome labels or calibration; the baseline is not a probability and cannot establish damage, coverage, claim validity, or outreach eligibility |
| Unauthorized source-driven alert | Acquisition mode and authorization basis are persisted; synthetic/live/unauthorized retrievals cannot satisfy the alert gate; Sarasota live polling remains disabled | Written source approvals and production alert policy remain external gates |
| Dashboard implies records or freshness that are not present | Explicit loading, API-unavailable, and empty states; Sarasota manual-source pill and disabled-live banner; browser health check is advisory | Authenticated domain reads, deployment controls, and production observability remain later hardening work |
| Dashboard overstates map/property/score certainty | Map, workbench, and property surfaces remain empty until governed data exists; ranking copy says provisional/non-probability; no damage, coverage, claim-validity, or outreach claims | Human review and later outcomes/model gates are still required before operational use |
| Browser treated as an authorization boundary | UI states that API role checks are authoritative; no browser-only sensitive record access or source activation control; trusted-host/CORS/API security headers | Full production identity/MFA and domain deployment remain external gates |

## Phase 10 controls and residuals

- `TrustedHostMiddleware` plus explicit production `ALLOWED_HOSTS` constrains Host-header ambiguity. Production settings reject wildcard hosts and HTTP origins.
- Request `Content-Length`, streamed file bytes, safe filenames/suffixes, ZIP member paths/count, and uncompressed archive size are bounded. API responses use no-store and security headers.
- Redis is required for staging/production rate limiting and readiness; the memory limiter is a local fallback only. Redis failures fail closed on protected writes.
- Audit events form a sequence/hash chain and expose a verification result. A mismatch is an operational incident; repair is not automatic.
- Backups are checksummed, restore targets are explicit, bundled raw payloads are restored with the database, payload retention is dry-run-first, and purged dispatch/property payloads retain source-row/provenance tombstones. Retention uses a pending marker and per-payload audit commits so a storage failure cannot silently roll back an already-deleted byte's database record.
- Observability is payload-minimal and bounded. Metrics are in-process until a deployment binds `/metrics` to a monitored collector; `ERROR_TRACKING_DSN` is only an integration point.
- The host could not execute PostgreSQL/PostGIS, Redis, managed object storage, or managed recovery. These are not represented as passed controls.

## Required production follow-up

Before production use, complete deployment-owner identity/MFA, secret management/rotation, managed TLS/domain, PostgreSQL/PostGIS/Redis/R2 provisioning, staging restore/readiness exercises, source approvals, and the external activation checklist. This document records a hardening implementation and residuals; it is not a production security approval.
