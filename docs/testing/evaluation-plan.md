# Evaluation plan

## Phase 1 gate

- Clean dependency install from README.
- Alembic upgrade and downgrade work against local SQLite; Compose service definitions are syntactically reviewable for PostgreSQL/PostGIS and Redis.
- Bootstrap creates one administrator and closes after first user.
- Invalid credentials and protected routes fail closed.
- Provider registry exposes fixture and disabled live provider.
- Provider disable action is administrator-only and audited.
- Health/readiness endpoints run.
- Web shell produces a production build.

## Test layers

1. Unit: password/session hashing, provider contract behavior, fixture shape.
2. Integration: migrations, auth flow, role checks, audit persistence, provider seeding.
3. API smoke: health, one-time bootstrap, login, provider list, identity.
4. Web build: TypeScript compilation and production Next.js build.
5. Future end-to-end: approved snapshot import through outcome capture, only after phases 2–8 exist.

## Future model evaluation

Measure technical accuracy separately from conversion: precision/recall/PR-AUC and calibration for incident classification; top-1/top-3, MRR, and abstention for property resolution; precision at 5/10/25 and NDCG for ranking; latency, acknowledgment, review yield, and found-first outcomes operationally. Use time-based, incident-grouped, and property-grouped splits with leakage tests. No current accuracy claim is made.
