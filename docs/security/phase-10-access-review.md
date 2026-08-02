# Phase 10 access and authorization review

## Review posture

The API is the authorization boundary. Browser controls are convenience states only. Every protected route resolves a database session and server-side role dependency. This review covers the implemented local/runtime path; it is not an approval for production identity or legal use.

| Capability | Roles | Control | Audit expectation |
| --- | --- | --- | --- |
| Sign in, sign out, own identity | authenticated session | hashed bearer token, expiry, idle timeout, revocation, replacement cap | login/logout/bootstrap events |
| Provider/source administration | administrator | provider mutation and health controls require `administrator` | provider actions |
| Snapshot/dispatch ingestion | administrator, analyst, researcher | manual/file route, size/suffix checks, acquisition mode and approval basis persisted | import/retrieval/process events |
| Incident edits and merge/split | administrator, analyst | `IncidentEditor`; source rows and decisions remain immutable | merge/split/state events |
| Property import | administrator, analyst, researcher | `PropertyImporter`; official provider attestation remains explicit | import/rollback events |
| Property review | administrator, licensed_adjuster, analyst | `PropertyReviewer`; confirm/reject/correct are append-only decisions | review events |
| Opportunity review | administrator, licensed_adjuster, analyst | `OpportunityReviewer`; overrides never rewrite baseline score | override/rollback events |
| Workflow assignment/notes | administrator, analyst | internal-only routes; notes append-only | assignment/note events |
| Outcome labels/analytics | authenticated reviewer routes | controlled taxonomy, provenance, idempotency, as-of boundary | label/report events |
| Learning controls | administrator for release controls; authenticated reads | model activation requires explicit data/approval gates and serving flag; flag remains false | control actions |
| Audit and operations inspection | administrator | audit chain integrity and dependency state are admin-only | audit reads are themselves observable |

## Secure defaults verified

- Development bootstrap is enabled only for local setup and is closed after the first user. Production/staging reject bootstrap enabled, the development password, SQLite, HTTP origins, wildcard hosts, memory rate limiting, non-ready Redis, and API docs.
- `ALLOWED_HOSTS` is explicit outside development and enforced by `TrustedHostMiddleware`.
- Login/bootstrap and file-import POSTs have bounded rate limits. Redis-backed limits fail closed in staging/production; the bounded memory limiter is a development fallback only.
- Sessions store only a hash, expire, have an idle timeout, cap active sessions, and mark replaced/revoked sessions invalid.
- File names, suffixes, content length, archive member count, archive path safety, and uncompressed archive bytes are validated before import.
- Sarasota live polling and learned serving are false in all checked-in environment/deployment templates.
- No browser route can enable a provider, legal approval, learned serving, or consumer outreach.

## Residual gates

Production SSO/MFA, enterprise user provisioning, secret rotation, managed database/Redis/R2 provisioning, TLS/domain ownership, and an operational access review by the deployment owner remain external deployment gates. No permission or legal approval is invented by this repository.
