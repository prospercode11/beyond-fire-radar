# System context and data flow

```mermaid
flowchart LR
  A[Authorized external sources] --> B[Provider contracts]
  F[Synthetic fixtures] --> B
  B --> C[Immutable raw snapshots]
  C --> D[Versioned normalization and future domain pipelines]
  D --> E[(PostgreSQL + PostGIS)]
  E --> API[FastAPI modular monolith]
  API --> WEB[Next.js internal web client]
  API --> AUDIT[(Immutable audit events)]
  API -. future jobs .-> REDIS[(Redis)]
  LEGAL[Legal approvals and feature flags] --> API
  REVIEW[Authorized human reviewers] --> WEB
  REVIEW --> OUT[Manual outcomes and labels]
  OUT --> E
```

## Trust boundaries

1. External sources are untrusted input and must be authorized before activation.
2. Raw source data is retained separately from normalized records.
3. The API is the authorization boundary; the browser is not trusted.
4. Owner and organization data is restricted and is never automatically contacted.
5. Model outputs are governed artifacts, not facts.

## Phase 2 through Phase 4 request flow

```mermaid
sequenceDiagram
  participant U as Authorized user
  participant W as Web shell/API client
  participant A as FastAPI
  participant DB as SQL database
  U->>W: Sign in
  W->>A: POST /api/v1/auth/login
  A->>DB: Verify password and create session hash
  DB-->>A: Session
  A-->>W: Bearer token and role claims
  W->>A: GET /api/v1/providers
  A->>DB: Check session and role
  DB-->>A: Provider metadata
  A-->>W: Authorized provider list
  U->>W: Upload approved dispatch snapshot
  W->>A: POST /providers/{id}/snapshots + Idempotency-Key
  A->>DB: Persist retrieval, job, raw reference, parse result, health, audit
  A-->>W: Status, counts, parser/schema version, replay state
  U->>W: Start incident processing for a manual retrieval
  W->>A: POST /incidents/process/retrievals/{retrieval_id}
  A->>DB: Verify acquisition mode, assemble/link observations, persist decisions/evidence/timeline
  A-->>W: Processing counts, linkage/classification versions, review/contradiction counts
  U->>W: Preview/import a manually supplied property file
  W->>A: POST /properties/imports/preview or /properties/imports
  A->>DB: Verify provider type/attestation, persist raw file, source rows, projections, provenance, audit
  U->>W: Request property candidates or record human review decision
  W->>A: POST /incidents/{id}/property-matches or /property-matches/decisions
  A->>DB: Generate versioned candidates, preserve evidence, or persist reviewed decision
  A-->>W: Candidates, abstention, explanations, provenance, and review state
```

Manual snapshot ingestion and Sarasota-only incident processing are the Phase 2/3 boundary. Phase 4 adds manual/file property workflows only. Dispatch retrievals carry `manual_snapshot` or `synthetic_fixture` provenance; official property imports require an explicit authorization attestation and synthetic fixture imports are labeled separately. Live-collected input and automated official property retrieval remain disabled. The external approval gate is not removed or bypassed. No Boca radio, Broadcastify, scoring, dashboard, or outreach source is in scope.
