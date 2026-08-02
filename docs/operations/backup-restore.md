# Backup, restore, and retention

## Local SQLite

The safe local bundle commands are:

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/backup.py create \
  --database-url "$DATABASE_URL" --raw-dir data/raw-snapshots --output /tmp/bfr-backup.zip
PATH="$PWD/.venv/bin:$PATH" python scripts/backup.py verify --bundle /tmp/bfr-backup.zip
PATH="$PWD/.venv/bin:$PATH" python scripts/backup.py restore --bundle /tmp/bfr-backup.zip \
  --target-database /tmp/bfr-restored.db --target-raw-dir /tmp/bfr-restored-raw
```

Restore refuses to overwrite an existing database or raw directory without `--force`. If a bundle contains raw payloads, `--target-raw-dir` is required; the restore stages and checksum-verifies every payload before replacing the target directory. Bundles include a copied SQLite database, a manifest, database checksum, and raw-file checksums. The test suite verifies both the copied row and raw payload survive restore.

## PostgreSQL/PostGIS

Use a managed provider's encrypted automated backups and point-in-time recovery where available. The API release image includes the schema migrations; the operational dump command is:

```bash
pg_dump --format=custom --file=/secure/location/bfr-$(date +%Y%m%dT%H%M%SZ).dump "$DATABASE_URL"
pg_restore --clean --if-exists --dbname="$RESTORE_DATABASE_URL" /secure/location/bfr-<timestamp>.dump
```

Restore into an isolated database first. Run `alembic upgrade head`, `/readyz`, the audit-integrity endpoint, and the clean API smoke before changing a service connection. Exact RPO/RTO numbers are deployment targets to be measured with the selected provider, not claims made by this repository.

## Raw snapshots and retention

Local raw payloads are content-addressed. Production uses the S3-compatible adapter for Cloudflare R2 or an equivalent approved store. Configure bucket versioning/retention and environment isolation at the provider. `scripts/retention.py` is dry-run by default:

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/retention.py --days 365
PATH="$PWD/.venv/bin:$PATH" python scripts/retention.py --days 365 --apply --confirm
```

Apply mode covers dispatch raw snapshots and property imports. Each item is marked pending and audited before deletion, then receives a committed tombstone and completion audit event only after deletion succeeds. A failure leaves the pending marker for retry/reconciliation; an already-missing payload is recorded as reconciled. A purged dispatch payload endpoint returns 410; retention does not rewrite incidents or source-row relationships. Confirm the backup and legal retention policy before using apply mode.
