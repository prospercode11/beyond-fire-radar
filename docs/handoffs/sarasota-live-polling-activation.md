# Sarasota live polling activation handoff

Updated: 2026-08-02

## Outcome

The existing Sarasota County dispatch adapter and scheduler are enabled for the local development test server only. The worker performs an immediate retrieval when the API starts and then runs at the configuration-enforced interval of exactly 900 seconds (15 minutes). A database lease prevents overlapping workers.

The current local authorization basis is `explicit_user_permission`, supplied by the operator in this task. This is not a legal approval. Staging and production remain fail-closed until a persisted `LegalApproval` for `sarasota.dispatch.live_polling` is approved and timestamped. The checked-in `.env.example`, Render template, and production/staging templates remain disabled by default.

## Source and provenance

- Initial source: Sarasota County 911 Dispatch Reporting, `https://dispatchreporting.scgov.net/Events?strAgencyID=All`.
- Retrieval method: normal HTTPS GET only; no CAPTCHA, access-control, rate-limit, or terms bypass.
- Live records use `acquisition_mode=live_poll` and retain provider, retrieval, raw snapshot, parser/schema, processing-run, authorization-basis, health, and audit references.
- Manual snapshots, CSV/JSON/HTML files, fixtures, and replay remain available and are visibly distinguished from live-collected data.
- Live-poll evidence cannot create operational alerts; the existing alert gate still requires explicitly authorized manual dispatch evidence.

## Verification result

The real endpoint was retrieved and parsed successfully: 57 normalized source rows and no parser issues were observed during the activation check. A database-backed live poll completed with retrieval and processing references. Repeated live retrieval/processing kept the current local canonical incident count stable at 60, demonstrating idempotency for the observed Sarasota snapshot sequence without making any real-world accuracy claim.

After the web proxy/runtime correction, the scheduled worker completed another real cycle at 2026-08-02 17:40:51 UTC, exactly 900 seconds after the prior 17:25:50 UTC cycle, with 56 normalized rows, `live_poll` raw/processing provenance, a completed lease, zero failures, and a closed circuit.

The standalone web server defaults to a same-origin `/api-backend` proxy for local API access because the in-app browser blocks direct local cross-port navigation. The browser now reads the proxied `/healthz` response and displays the actual runtime state, including `Enabled · every 15 minutes`, while preserving the approval-gated language. The test server is available at [http://127.0.0.1:3021/](http://127.0.0.1:3021/) with the direct API health endpoint at [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz).

## Final verification

- `./scripts/verify.sh`: passed; 61 Python tests, Ruff, mypy, ESLint, and Next production build passed.
- `PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py migrate`: passed at migration head `0024_scope_snapshot_replay_by_acquisition`.
- `PATH="$PWD/.venv/bin:$PATH" API_BASE_URL=http://127.0.0.1:8000 python scripts/dev.py api-smoke`: passed.
- `PATH="$PWD/.venv/bin:$PATH" API_BASE_URL=http://127.0.0.1:8000 python scripts/e2e_acceptance.py`: passed.
- `/healthz`: `live_polling_enabled=true`, `live_polling_worker_enabled=true`, `live_polling_interval_seconds=900`.
- Official Sarasota provider health: last status `imported`, failure count `0`, circuit `closed`; latest observed live retrieval contained 56 normalized rows.
- Authenticated browser acceptance after the proxy correction: 60 canonical incidents, current source freshness, mixed live/manual provenance, no error banner, and `Enabled · every 15 minutes`.

## Required commands

```bash
./scripts/verify.sh
python scripts/dev.py migrate
API_BASE_URL=http://127.0.0.1:8000 python scripts/dev.py api-smoke
API_BASE_URL=http://127.0.0.1:8000 python scripts/e2e_acceptance.py
```

The final command outputs and commit are recorded in the closing task response and should be rerun after any environment or source configuration change.

## Explicit stop boundary

No Phase 4 property ingestion changes, address-to-parcel matching, new scoring work, new machine learning, Boca/Broadcastify integration, consumer outreach, or final dashboard work is included in this activation.
