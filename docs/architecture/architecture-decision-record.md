# Architecture decision record

Date: 2026-07-31
Status: accepted for Phase 0/1/2 implementation boundary
Decision owner: implementation agent

## Decision

Use a modular monolith with a FastAPI/SQLAlchemy backend, Alembic migrations, PostgreSQL/PostGIS as the production relational store, Redis as the future job/cache dependency, and a Next.js/TypeScript web client. Local development uses SQLite when PostgreSQL is unavailable, but production schemas and deployment require PostgreSQL/PostGIS.

## Why

The product needs strong relational integrity, auditability, temporal provenance, and geospatial capability. A modular monolith keeps those boundaries explicit without premature distributed-service failure modes. FastAPI and TypeScript provide typed HTTP contracts; Alembic makes database changes reproducible; Redis is reserved for background-job coordination rather than hidden state.

## Phase 1 and Phase 2 boundaries

- No live poller, property matcher, scoring model, or notifications are activated.
- The Sarasota provider interface fails closed when authorization or the feature flag is absent; Phase 2 adds a manual snapshot path with explicit attestation.
- The schema includes governance, provider, raw-snapshot, retrieval, import-job, parser, schema-alert, raw-row, observation, and import-error records; canonical domain tables are added by later gated phases.
- PostGIS is provided by Compose and reserved for the parcel/geometry phase; Phase 1 does not fake spatial behavior with a text field.

## Alternatives rejected

- **Microservices:** not justified before measured throughput or team ownership boundaries exist.
- **Prompt-defined mechanics:** deterministic access, provenance, authorization, and model-version behavior must live in code and migrations.
- **Open user registration:** internal access starts with one-time configured bootstrap, then administrator-controlled provisioning in a later auth-management slice.
- **Live scraping/polling:** source authorization and terms remain unverified; the safe state is a visible disabled provider plus an authorized manual snapshot path.

## Invariants

1. Raw source payloads are immutable and content-addressed.
2. A provider failure never deletes prior provider data.
3. Authentication and authorization are checked server-side.
4. Security-sensitive actions produce audit records.
5. A displayed probability must be calibrated against real held-out labels; Phase 1 displays no such probabilities.
6. Consumer outreach is outside the product boundary.
