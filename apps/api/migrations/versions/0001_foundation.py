"""create governed foundation tables

Revision ID: 0001_foundation
Revises:
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            sa.String(36),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "actor_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("event_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"])
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    op.create_table(
        "providers",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_authority", sa.String(200), nullable=False),
        sa.Column("geographic_coverage", sa.String(200), nullable=False),
        sa.Column("data_type", sa.String(100), nullable=False),
        sa.Column("authentication_method", sa.String(100), nullable=False),
        sa.Column("authorized_use_status", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("polling_interval_seconds", sa.Integer(), nullable=True),
        sa.Column("schema_version", sa.String(50), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=False),
        sa.Column("contact_note", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "provider_retrievals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_hash", sa.String(64), nullable=True),
        sa.Column("normalized_record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("circuit_state", sa.String(40), nullable=False, server_default="closed"),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_provider_retrievals_provider_id", "provider_retrievals", ["provider_id"])
    op.create_index(
        "ix_provider_retrievals_snapshot_hash", "provider_retrievals", ["snapshot_hash"]
    )

    op.create_table(
        "raw_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column(
            "retrieval_id", sa.String(36), sa.ForeignKey("provider_retrievals.id"), nullable=False
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("payload_reference", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("retrieval_id", name="uq_raw_snapshots_retrieval_id"),
        sa.UniqueConstraint("content_hash", name="uq_raw_snapshots_content_hash"),
    )
    op.create_index("ix_raw_snapshots_provider_id", "raw_snapshots", ["provider_id"])
    op.create_index("ix_raw_snapshots_content_hash", "raw_snapshots", ["content_hash"])

    op.create_table(
        "feature_flags",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "legal_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("approved_by", sa.String(200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
    )
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_import_jobs_idempotency_key"),
    )
    op.create_index("ix_import_jobs_provider_id", "import_jobs", ["provider_id"])
    op.create_table(
        "provider_health",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("last_successful_retrieval", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_changed_retrieval", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("circuit_state", sa.String(40), nullable=False, server_default="closed"),
        sa.Column("schema_drift_detected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("known_status_note", sa.Text(), nullable=False),
        sa.UniqueConstraint("provider_id", name="uq_provider_health_provider"),
    )


def downgrade() -> None:
    op.drop_table("provider_health")
    op.drop_index("ix_import_jobs_provider_id", table_name="import_jobs")
    op.drop_table("import_jobs")
    op.drop_table("legal_approvals")
    op.drop_table("feature_flags")
    op.drop_index("ix_raw_snapshots_content_hash", table_name="raw_snapshots")
    op.drop_index("ix_raw_snapshots_provider_id", table_name="raw_snapshots")
    op.drop_table("raw_snapshots")
    op.drop_index("ix_provider_retrievals_snapshot_hash", table_name="provider_retrievals")
    op.drop_index("ix_provider_retrievals_provider_id", table_name="provider_retrievals")
    op.drop_table("provider_retrievals")
    op.drop_table("providers")
    for name in [
        "ix_audit_events_created_at",
        "ix_audit_events_request_id",
        "ix_audit_events_resource_id",
        "ix_audit_events_action",
        "ix_audit_events_actor_user_id",
    ]:
        op.drop_index(name, table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_token_hash", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
