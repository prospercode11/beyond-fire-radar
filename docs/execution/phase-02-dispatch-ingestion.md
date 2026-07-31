# Phase 2 — Dispatch ingestion

## Scope

Authorized snapshot upload, CSV/HTML parsing, raw preservation, taxonomy configuration, schema-drift detection, provider health, idempotent replay, and a disabled live-polling interface.

## Gate

Approved snapshot parses; parser failures and zero-row anomalies are visible; duplicate replay creates no duplicate raw/normalized records; contract tests pass; live polling remains disabled unless written authorization exists.
