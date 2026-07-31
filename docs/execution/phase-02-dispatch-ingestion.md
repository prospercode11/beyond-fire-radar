# Phase 2 — Dispatch ingestion

## Scope

Authorized snapshot upload, CSV/HTML parsing, raw preservation, taxonomy configuration, schema-drift detection, provider health, idempotent replay, and a disabled live-polling interface.

## Implemented boundary

The initial source is the [Sarasota County 911 Dispatch Reporting interface](https://dispatchreporting.scgov.net/Events?strAgencyID=All). Phase 2 uses it as the source contract and parser shape. The implementation does not poll it: `ENABLE_LIVE_SARASOTA_DISPATCH_POLLING=false` remains the default and the live provider raises a visible disabled error. Manual uploads to `sarasota.official_dispatch` require an explicit `authorized_snapshot=true` attestation.

Implemented endpoints:

- `POST /api/v1/providers/{provider_id}/snapshots`
- `GET /api/v1/providers/{provider_id}/health`
- `GET /api/v1/providers/{provider_id}/parser-versions`
- `GET /api/v1/providers/{provider_id}/retrievals`
- `GET /api/v1/providers/{provider_id}/parser-compare`
- `GET /api/v1/retrievals/{retrieval_id}/observations`
- `GET /api/v1/retrievals/{retrieval_id}/raw`
- `GET /api/v1/retrievals/{retrieval_id}/schema-alerts`
- `GET /api/v1/retrievals/{retrieval_id}/errors`

The parser preserves source wording, source case/event identifiers, original location, grid/zone, raw payload bytes, row payloads, parser/taxonomy versions, and retrieval timestamps. It classifies only explicit source-supported event wording; unsupported wording is retained as `Unknown fire situation` rather than promoted to a working-fire claim.

## Acceptance gate

- [x] Deterministic CSV and HTML contract fixtures parse with source identifiers and event taxonomy.
- [x] Parser failure is visible through retrieval status, import errors, schema alerts, and provider health.
- [x] Zero-row anomaly is visible and does not replace prior usable data.
- [x] Duplicate replay returns the original retrieval and creates no duplicate raw or normalized rows.
- [x] Migration upgrade/downgrade/upgrade, API tests, parser tests, lint, type checks, and web verification pass.
- [x] Live polling remains disabled and no access-control, CAPTCHA, or rate-limit bypass exists.
- [ ] A Sarasota snapshot with written approval is still required to close the external-source gate. The current public page was used only for one-time parser shape verification.

Phase 3 is not started. No canonical incident, property resolution, scoring, outreach, or Boca/Broadcastify work belongs in this phase.
