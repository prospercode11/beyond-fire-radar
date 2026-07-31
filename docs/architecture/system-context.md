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

## Phase 1 request flow

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
```

The raw provider retrieval and domain pipelines are not part of Phase 1; the registry contract is testable without pretending an external feed was retrieved.
