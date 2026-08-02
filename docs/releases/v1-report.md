# Beyond Fire Radar v1 release report

## Delivered

Phases 0–9 deliver the governed Sarasota manual-dispatch prototype through inactive learning infrastructure: source-preserving ingestion, canonical incident intelligence, property-file resolution, explainable non-probability ranking, internal dashboard/workflow, outcomes/analytics, and blocked learned-model controls. Phase 10 adds production-hardening mechanics: secure configuration, trusted hosts, request/upload/archive limits, rate limiting, session lifecycle, audit-chain integrity, structured observability, backup/restore, retention, object-storage adapter, deployment images/configuration, runbooks, and final acceptance evidence.

## Source and safety posture

Sarasota County dispatch records remain the only initial source. Manual snapshots, CSV/JSON/HTML files, fixtures, and replay are labeled by acquisition mode. Live Sarasota polling is disabled; the external-source approval gate remains intact. Boca, Broadcastify, consumer outreach, owner contact, legal conclusions, coverage/claim inference, and learned serving are not part of v1.

## Local startup

```bash
cp .env.example .env
PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py migrate
PATH="$PWD/.venv/bin:$PATH" python scripts/dev.py local
```

Open `http://localhost:3000`. The development API is `http://127.0.0.1:8000`; bootstrap credentials come from `.env` and are local-only. Production/staging bootstrap is rejected by configuration.

## Deployment readiness

`apps/api/Dockerfile`, `apps/web/Dockerfile`, `render.yaml`, `.env.staging.example`, `.env.production.example`, `docs/deployment/guide.md`, and the operations runbooks provide the deployment boundary. Managed services, secrets, identity/MFA, TLS/domain, source approvals, and real recovery exercises remain operator-owned gates.

## Verification and limitations

The Phase 10 handoff records exact final command output, isolated database/replay evidence, browser evidence, and independent Luna findings/remediation. The host cannot run Docker/Colima, so PostgreSQL/PostGIS/Redis/R2 execution is explicitly unavailable. Fixtures are not accuracy evidence. See `docs/operations/known-limitations.md` and `docs/compliance/external-activation-checklist.md` before any activation.
