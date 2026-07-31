# Foundation data model

Phase 1 migration `0001_foundation` creates the governance and source-control core.

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
```

The provider and raw-snapshot records capture source authority, authorized-use state, schema/parser versions, snapshot hashes, retrieval status, failure state, and limitations. Later migrations will add incidents, observations, parcels, candidates, features, labels, opportunities, and workflow records without mutating this provenance contract.
