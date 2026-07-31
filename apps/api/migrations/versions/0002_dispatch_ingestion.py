"""add dispatch ingestion, parser, and schema health tables

Revision ID: 0002_dispatch_ingestion
Revises: 0001_foundation
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_dispatch_ingestion"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_retrievals",
        sa.Column("schema_version", sa.String(50), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "provider_retrievals",
        sa.Column("parser_version", sa.String(50), nullable=False, server_default="unknown"),
    )

    with op.batch_alter_table("import_jobs", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "request_hash", sa.String(64), nullable=False, server_default="legacy-unavailable"
            )
        )
        batch_op.add_column(
            sa.Column(
                "retrieval_id",
                sa.String(36),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_import_jobs_retrieval_id", "provider_retrievals", ["retrieval_id"], ["id"]
        )
    op.create_index("ix_import_jobs_retrieval_id", "import_jobs", ["retrieval_id"])

    op.add_column(
        "provider_health", sa.Column("last_retrieval_status", sa.String(40), nullable=True)
    )
    op.add_column(
        "provider_health",
        sa.Column("schema_alert_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "parser_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("format", sa.String(40), nullable=False),
        sa.Column("expected_fields", sa.JSON(), nullable=False),
        sa.Column("required_fields", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("provider_id", "version", name="uq_parser_versions_provider_version"),
    )
    op.create_index("ix_parser_versions_provider_id", "parser_versions", ["provider_id"])

    op.create_table(
        "schema_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column(
            "retrieval_id", sa.String(36), sa.ForeignKey("provider_retrievals.id"), nullable=False
        ),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("observed_fields", sa.JSON(), nullable=False),
        sa.Column("missing_required_fields", sa.JSON(), nullable=False),
        sa.Column("unexpected_fields", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_schema_alerts_provider_id", "schema_alerts", ["provider_id"])
    op.create_index("ix_schema_alerts_retrieval_id", "schema_alerts", ["retrieval_id"])

    op.create_table(
        "raw_dispatch_rows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "raw_snapshot_id", sa.String(36), sa.ForeignKey("raw_snapshots.id"), nullable=False
        ),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_record_id", sa.String(200), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "raw_snapshot_id", "row_number", name="uq_raw_dispatch_rows_snapshot_row"
        ),
    )
    op.create_index(
        "ix_raw_dispatch_rows_raw_snapshot_id", "raw_dispatch_rows", ["raw_snapshot_id"]
    )
    op.create_index("ix_raw_dispatch_rows_provider_id", "raw_dispatch_rows", ["provider_id"])
    op.create_index(
        "ix_raw_dispatch_rows_source_record_id", "raw_dispatch_rows", ["source_record_id"]
    )

    op.create_table(
        "dispatch_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "raw_dispatch_row_id",
            sa.String(36),
            sa.ForeignKey("raw_dispatch_rows.id"),
            nullable=False,
        ),
        sa.Column(
            "raw_snapshot_id", sa.String(36), sa.ForeignKey("raw_snapshots.id"), nullable=False
        ),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("source_record_id", sa.String(200), nullable=False),
        sa.Column("source_event_id", sa.String(100), nullable=True),
        sa.Column("source_case_number", sa.String(100), nullable=True),
        sa.Column("agency", sa.String(120), nullable=True),
        sa.Column("station", sa.String(200), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_event_type", sa.String(200), nullable=False),
        sa.Column("normalized_event_family", sa.String(100), nullable=False),
        sa.Column("original_location", sa.Text(), nullable=False),
        sa.Column("grid", sa.String(50), nullable=True),
        sa.Column("parser_confidence", sa.Float(), nullable=False),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("taxonomy_version", sa.String(50), nullable=False),
        sa.Column("raw_payload_reference", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("raw_dispatch_row_id", name="uq_dispatch_observations_raw_row"),
    )
    op.create_index(
        "ix_dispatch_observations_raw_snapshot_id", "dispatch_observations", ["raw_snapshot_id"]
    )
    op.create_index(
        "ix_dispatch_observations_provider_id", "dispatch_observations", ["provider_id"]
    )
    op.create_index(
        "ix_dispatch_observations_source_record_id", "dispatch_observations", ["source_record_id"]
    )
    op.create_index(
        "ix_dispatch_observations_source_event_id", "dispatch_observations", ["source_event_id"]
    )
    op.create_index(
        "ix_dispatch_observations_source_case_number",
        "dispatch_observations",
        ["source_case_number"],
    )
    op.create_index("ix_dispatch_observations_event_time", "dispatch_observations", ["event_time"])
    op.create_index(
        "ix_dispatch_observations_normalized_event_family",
        "dispatch_observations",
        ["normalized_event_family"],
    )

    op.create_table(
        "import_errors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_job_id", sa.String(36), sa.ForeignKey("import_jobs.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_import_errors_import_job_id", "import_errors", ["import_job_id"])


def downgrade() -> None:
    op.drop_index("ix_import_errors_import_job_id", table_name="import_errors")
    op.drop_table("import_errors")
    for name in [
        "ix_dispatch_observations_normalized_event_family",
        "ix_dispatch_observations_event_time",
        "ix_dispatch_observations_source_case_number",
        "ix_dispatch_observations_source_event_id",
        "ix_dispatch_observations_source_record_id",
        "ix_dispatch_observations_provider_id",
        "ix_dispatch_observations_raw_snapshot_id",
    ]:
        op.drop_index(name, table_name="dispatch_observations")
    op.drop_table("dispatch_observations")
    for name in [
        "ix_raw_dispatch_rows_source_record_id",
        "ix_raw_dispatch_rows_provider_id",
        "ix_raw_dispatch_rows_raw_snapshot_id",
    ]:
        op.drop_index(name, table_name="raw_dispatch_rows")
    op.drop_table("raw_dispatch_rows")
    op.drop_index("ix_schema_alerts_retrieval_id", table_name="schema_alerts")
    op.drop_index("ix_schema_alerts_provider_id", table_name="schema_alerts")
    op.drop_table("schema_alerts")
    op.drop_index("ix_parser_versions_provider_id", table_name="parser_versions")
    op.drop_table("parser_versions")
    with op.batch_alter_table("provider_health", recreate="always") as batch_op:
        batch_op.drop_column("schema_alert_count")
        batch_op.drop_column("last_retrieval_status")
    op.drop_index("ix_import_jobs_retrieval_id", table_name="import_jobs")
    with op.batch_alter_table("import_jobs", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_import_jobs_retrieval_id", type_="foreignkey")
        batch_op.drop_column("retrieval_id")
        batch_op.drop_column("request_hash")
    with op.batch_alter_table("provider_retrievals", recreate="always") as batch_op:
        batch_op.drop_column("parser_version")
        batch_op.drop_column("schema_version")
