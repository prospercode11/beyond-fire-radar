# Operations runbook

## Health and observability

- `/healthz` is a liveness response and reports environment, live-polling flag, learned-serving flag, and phase.
- `/readyz` verifies the database and, when configured, Redis. A production Redis failure returns 503.
- `/metrics` exposes bounded Prometheus text for request counts and median/0.99 duration samples. It contains no source payloads or bearer tokens.
- HTTP logs are one-line JSON with method, route template, status, duration, and request ID. Configure `LOG_LEVEL` and an external error tracker through `ERROR_TRACKING_DSN`; no secret or payload logging is enabled by default.
- `/api/v1/admin/operations` reports database connectivity, pending in-app notification jobs, provider circuit state, live polling, and learned serving to administrators.
- `/api/v1/admin/audit/integrity` verifies event sequence, previous hashes, event hashes, and the chain head.

## Failure response

1. Check `/healthz`, `/readyz`, `/metrics`, and structured logs using the request ID.
2. If Redis is unavailable, do not enable production traffic until readiness returns; the limiter fails closed for protected POST surfaces.
3. If object storage is unavailable, stop imports and preserve retrieval metadata; do not retry with a different source or delete provenance.
4. If a migration fails, stop the release, retain the previous deployment and backup, and restore only into an isolated target for diagnosis.
5. If audit integrity fails, freeze administrative mutations, preserve the database, record the incident, and investigate the first invalid sequence before any repair.
6. Keep Sarasota live polling and learned serving disabled during every recovery action.

## Queue/worker posture

Notification jobs are internal in-app jobs only. The operations endpoint exposes pending counts and oldest pending time; no consumer or external channel is configured. A future worker must claim jobs transactionally, bound retries, record errors, and emit audit events before it is enabled. Current local API behavior is synchronous and does not imply a worker SLA.

## Failure injection and recovery exercises

The automated suite injects audit tampering, object-storage payload tampering, rate-limit concurrency, unsafe uploads/archives, and backup restore. Before a production activation, the operator must repeat a database restore into an isolated environment, verify audit and raw references, test Redis/readiness loss, and test an R2 object read failure without changing the source gate.
