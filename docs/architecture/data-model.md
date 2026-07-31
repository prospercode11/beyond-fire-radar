# Foundation and dispatch-ingestion data model

Phase 1 migration `0001_foundation` creates the governance and source-control core. Phase 2 migration `0002_dispatch_ingestion` adds versioned parser contracts, failure visibility, and source-preserving dispatch observations.

```mermaid
erDiagram
  USERS ||--o{ USER_ROLES : has
  ROLES ||--o{ USER_ROLES : grants
  USERS ||--o{ SESSIONS : owns
  USERS ||--o{ AUDIT_EVENTS : causes
  PROVIDERS ||--o{ PROVIDER_RETRIEVALS : retrieves
  PROVIDERS ||--o{ RAW_SNAPSHOTS : stores
  PROVIDER_RETRIEVALS ||--|| RAW_SNAPSHOTS : materializes
  PROVIDERS ||--|| PROVIDER_HEALTH : reports
  PROVIDERS ||--o{ IMPORT_JOBS : accepts
  USERS ||--o{ IMPORT_JOBS : creates
  PROVIDERS ||--o{ PARSER_VERSIONS : registers
  PROVIDERS ||--o{ SCHEMA_ALERTS : reports
  PROVIDER_RETRIEVALS ||--o{ SCHEMA_ALERTS : detects
  RAW_SNAPSHOTS ||--o{ RAW_DISPATCH_ROWS : contains
  RAW_DISPATCH_ROWS ||--|| DISPATCH_OBSERVATIONS : normalizes
  IMPORT_JOBS ||--o{ IMPORT_ERRORS : records
```

The provider and raw-snapshot records capture source authority, authorized-use state, schema/parser versions, snapshot hashes, retrieval status, failure state, and limitations. Raw dispatch rows preserve the source payload at row level; observations retain original wording/location and only add the versioned, source-faithful taxonomy family. Later migrations will add canonical incidents, parcels, candidates, features, labels, opportunities, and workflow records without mutating this provenance contract.
