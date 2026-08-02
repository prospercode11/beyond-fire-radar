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

## Phase 2 gate

- Fresh SQLite migration upgrade, downgrade, and re-upgrade succeed.
- Sarasota CSV/HTML/JSON parser contracts preserve raw/source fields and version metadata.
- Parser failure, missing required fields, and zero-row anomalies are persisted and exposed through the API.
- Same-payload replay is idempotent at both idempotency-key and content-hash levels.
- Provider health records successful and failed retrieval state without deleting prior usable data.
- Live Sarasota polling remains disabled; no Boca radio or Broadcastify source is used.
- A real approved Sarasota snapshot must be attached separately to close the external-source gate; repository fixtures are not evidence.

## Phase 3 gate

- Fresh migration upgrade/downgrade/re-upgrade includes canonical incident tables and acquisition-mode provenance.
- Current Sarasota manual/fixture retrievals process through deterministic and probabilistic linkage without requiring live polling.
- Reprocessing a retrieval is idempotent and does not create duplicate canonical incidents.
- Duplicate agency rows, missing IDs, conflicting event types, reused identifiers, separate same-address fires, malformed rows, and human merge/split controls are covered.
- Match, possible-match, and non-match decisions retain features, thresholds, explanations, and linkage version.
- Contradictions remain visible in evidence and timelines; source observations and raw row IDs remain inspectable.
- Manual state transitions reject unsupported states/transitions and are audited.
- No Phase 4 property, scoring, dashboard, outreach, Boca, Broadcastify, or broader machine-learning work is included.

## Phase 4 gate

- Fresh migration upgrade, downgrade, and re-upgrade include property imports, immutable source rows, parcels, aliases/buildings, field provenance, match runs, candidates, features, and human decisions.
- CSV, XLSX, and ZIP imports preserve original payloads/rows and support mapping previews, mixed valid header spellings, duplicate/rejected row reporting, full/incremental changes, replay, removals, and rollback along explicit import lineage.
- Address cases cover exact/unit/directional/street/block/intersection/highway/landmark/malformed locations; low-precision and unit-ambiguous incidents abstain and never expose an exact marker.
- Candidate generation and explanations expose address/alias/street/house/location/geographic/master-unit evidence, contradictions, quality flags, score/margin, versions, and review/abstention outcomes.
- Parcel API provenance exposes current import/source row/raw payload/field transformations/aliases/buildings; human property decisions survive reprocessing and are audited.
- The official property source approval gate remains open; the synthetic fixture is not evidence of real-world accuracy. PostgreSQL/PostGIS/Redis execution remains unavailable in this environment.

## Phase 5 gate

- Fresh migration upgrade, downgrade, and re-upgrade include scoring versions, score history, feature provenance, overrides, as-of, temporal incident-link intervals, and explicit predecessor rollback.
- Each scoring component is versioned and exposes value/status, contribution, available-at, source observations, evidence, and explanation. Missing, negative, and contradictory evidence stays visible and can hard-gate or abstain.
- Provisional ranking is explicitly non-probabilistic and uses a versioned weighted-geometric formula. No calibration, accuracy, insurance, coverage, claim-validity, or contact claim is permitted without real held-out evidence.
- Manual/fixture/live acquisition provenance is enforced: only explicitly authorized manual snapshots can meet the operational source gate, while synthetic and live/unauthorized sources remain ineligible for alerts and live Sarasota polling remains disabled.
- As-of scoring excludes observations, retrievals, property runs/decisions, property source projections, incident classifications, contradictory evidence, incident-link assignments, and freshness evidence after the prediction boundary. The contract evaluator rejects group overlap and future feature availability; it reports no accuracy metric.
- Human overrides are append-only, survive rescoring, do not mutate baseline runs, and score rollback follows an explicit predecessor with one current run per incident.
- Adversarial/API tests cover weak/negative events, missing or ambiguous property evidence, as-of boundaries, feature contributions, release registration, overrides, rescore, and rollback.
- Real outcome labels, calibration, production alert authorization, PostgreSQL/PostGIS/Redis execution, and later dashboard/outcome workflows remain external or later-phase gates.

## Test layers

1. Unit: password/session hashing, provider contract behavior, fixture shape.
2. Integration: migrations, auth flow, role checks, audit persistence, provider seeding.
3. API smoke: health, one-time bootstrap, login, provider list, identity.
4. Web build: TypeScript compilation and production Next.js build.
5. Future end-to-end: approved snapshot import through review/outcome capture, only after the relevant later phases exist.

## Future model evaluation

Measure technical accuracy separately from conversion: precision/recall/PR-AUC and calibration for incident classification; top-1/top-3, MRR, and abstention for property resolution; precision at 5/10/25 and NDCG for ranking; latency, acknowledgment, review yield, and found-first outcomes operationally. Use time-based, incident-grouped, and property-grouped splits with leakage tests. No current accuracy claim is made.
