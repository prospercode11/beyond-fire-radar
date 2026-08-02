"""add internal alerts, assignment history, notes, and existing-client imports"""

import sqlalchemy as sa
from alembic import op

revision = "0012_internal_workflow"
down_revision = "0011_temporal_incident_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "internal_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column(
            "score_run_id",
            sa.String(36),
            sa.ForeignKey("opportunity_score_runs.id"),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("alert_type", sa.String(48), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("evidence_snapshot", sa.JSON, nullable=False),
        sa.Column("suppression_reason", sa.Text, nullable=True),
        sa.Column("acknowledged_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_internal_alert_dedupe_key"),
    )
    op.create_index("ix_internal_alert_incident_id", "internal_alerts", ["incident_id"])
    op.create_index("ix_internal_alert_score_run_id", "internal_alerts", ["score_run_id"])
    op.create_index("ix_internal_alert_status_created", "internal_alerts", ["status", "created_at"])

    op.create_table(
        "notification_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_id", sa.String(36), sa.ForeignKey("internal_alerts.id"), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False, server_default="in_app"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("alert_id", "channel", name="uq_notification_alert_channel"),
    )
    op.create_index("ix_notification_jobs_alert_id", "notification_jobs", ["alert_id"])

    op.create_table(
        "incident_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column("assignee_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(40), nullable=False, server_default="reviewer"),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_incident_assignments_incident_id", "incident_assignments", ["incident_id"])
    op.create_index(
        "uq_incident_assignment_current",
        "incident_assignments",
        ["incident_id"],
        unique=True,
        sqlite_where=sa.text("ended_at IS NULL"),
        postgresql_where=sa.text("ended_at IS NULL"),
    )

    op.create_table(
        "workflow_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("note_type", sa.String(40), nullable=False, server_default="review"),
        sa.Column("author_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_workflow_notes_incident_id", "workflow_notes", ["incident_id"])

    op.create_table(
        "client_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(320), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("accepted_row_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rejected_row_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("raw_payload_reference", sa.Text, nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_client_import_idempotency"),
        sa.UniqueConstraint("content_hash", name="uq_client_import_content_hash"),
    )

    op.create_table(
        "existing_client_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "client_import_id", sa.String(36), sa.ForeignKey("client_imports.id"), nullable=False
        ),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("client_key", sa.String(160), nullable=False),
        sa.Column("normalized_address", sa.String(255), nullable=True),
        sa.Column("parcel_id", sa.String(160), nullable=True),
        sa.Column("do_not_contact", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source_note", sa.Text, nullable=True),
        sa.Column("raw_payload", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("client_import_id", "row_number", name="uq_client_import_row"),
    )
    op.create_index(
        "ix_existing_client_records_client_import_id",
        "existing_client_records",
        ["client_import_id"],
    )
    op.create_index("ix_existing_client_address", "existing_client_records", ["normalized_address"])
    op.create_index("ix_existing_client_parcel", "existing_client_records", ["parcel_id"])


def downgrade() -> None:
    op.drop_index("ix_existing_client_parcel", table_name="existing_client_records")
    op.drop_index("ix_existing_client_address", table_name="existing_client_records")
    op.drop_index(
        "ix_existing_client_records_client_import_id", table_name="existing_client_records"
    )
    op.drop_table("existing_client_records")
    op.drop_table("client_imports")
    op.drop_index("ix_workflow_notes_incident_id", table_name="workflow_notes")
    op.drop_table("workflow_notes")
    op.drop_index("uq_incident_assignment_current", table_name="incident_assignments")
    op.drop_index("ix_incident_assignments_incident_id", table_name="incident_assignments")
    op.drop_table("incident_assignments")
    op.drop_index("ix_notification_jobs_alert_id", table_name="notification_jobs")
    op.drop_table("notification_jobs")
    op.drop_index("ix_internal_alert_status_created", table_name="internal_alerts")
    op.drop_index("ix_internal_alert_score_run_id", table_name="internal_alerts")
    op.drop_index("ix_internal_alert_incident_id", table_name="internal_alerts")
    op.drop_table("internal_alerts")
