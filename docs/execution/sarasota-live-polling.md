# Sarasota live polling activation

## Scope

This is a narrowly scoped runtime activation for the existing Sarasota County dispatch provider. It does not start a later product phase and does not add Boca, Broadcastify, property polling, outreach, learned serving, or final dashboard work.

The official source is retrieved only with a normal HTTPS GET. The adapter does not bypass CAPTCHA, access controls, rate limits, robots/terms restrictions, or authentication. Manual snapshots, CSV/JSON/HTML files, fixtures, and replay remain available.

## Runtime contract

- `ENABLE_LIVE_SARASOTA_DISPATCH_POLLING` enables the provider path.
- `ENABLE_SARASOTA_POLLING_WORKER` starts the background scheduler.
- `SARASOTA_POLL_INTERVAL_SECONDS` is constrained in configuration to exactly `900` seconds.
- `SARASOTA_LIVE_AUTHORIZATION_BASIS=explicit_user_permission` is accepted only in local development for this operator activation. It is not a legal approval.
- Staging and production fail closed unless a persisted `LegalApproval` for `sarasota.dispatch.live_polling` has status `approved` and an approval timestamp.
- The worker executes one cycle at startup and then waits 900 seconds between cycles.
- A provider-scoped database lease prevents overlapping workers. Lease expiry permits recovery after a crashed process.
- Every cycle records acquisition mode, authorization basis, retrieval/raw snapshot references, processing run, provider health, and an audit outcome. Live retrieval bytes remain distinct from manual/fixture replay identity.
- Repeated identical live snapshots are idempotent and do not create duplicate canonical incidents.

## Local activation

The ignored local `.env` contains the activation values. `.env.example` and checked-in deployment templates remain disabled by default. The test server currently runs the API on `127.0.0.1:8000` and the standalone web app on `127.0.0.1:3021`.

## Acceptance evidence

- The real Sarasota endpoint returned an HTML response through the normal adapter; the parser accepted 57 rows with no parser issues during the activation check.
- A database-backed live poll retrieved and processed the source with acquisition mode `live_poll` and authorization basis `explicit_user_permission`.
- Repeated retrieval processing kept the observed canonical incident count stable at 60 in the current local database; this is an idempotency observation, not a model-accuracy claim.
- The API health contract reports the live flag, worker flag, and interval so the browser cannot display a stale disabled-only status.
- Manual and fixture workflows remain available, and live-poll evidence remains ineligible for operational alerts.

## Verification commands

From the repository root:

```bash
./scripts/verify.sh
python scripts/dev.py migrate
API_BASE_URL=http://127.0.0.1:8000 python scripts/dev.py api-smoke
API_BASE_URL=http://127.0.0.1:8000 python scripts/e2e_acceptance.py
```

Production/staging activation remains blocked pending source terms/approval evidence, managed services, and the external activation checklist.
