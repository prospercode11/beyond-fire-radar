"""add inactive-by-default learning datasets, models, replay, and drift records"""

import sqlalchemy as sa
from alembic import op

revision = "0017_learning_infrastructure"
down_revision = "0016_outcome_alert_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_feature_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(80), unique=True, nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("feature_names", sa.JSON, nullable=False),
        sa.Column("definitions", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "learning_label_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(80), unique=True, nullable=False),
        sa.Column("label_type", sa.String(48), nullable=False),
        sa.Column("positive_values", sa.JSON, nullable=False),
        sa.Column("negative_values", sa.JSON, nullable=False),
        sa.Column("excluded_values", sa.JSON, nullable=False),
        sa.Column("definition", sa.Text, nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "training_dataset_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(320), nullable=False),
        sa.Column("dataset_version", sa.String(80), nullable=False),
        sa.Column(
            "feature_set_id",
            sa.String(36),
            sa.ForeignKey("learning_feature_sets.id"),
            nullable=False,
        ),
        sa.Column(
            "label_set_id", sa.String(36), sa.ForeignKey("learning_label_sets.id"), nullable=False
        ),
        sa.Column(
            "source_manifest_id",
            sa.String(36),
            sa.ForeignKey("evaluation_manifests.id"),
            nullable=False,
        ),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("mechanics_only", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("real_data_eligible", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("row_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("incident_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("filters", sa.JSON, nullable=False),
        sa.Column("source_provenance", sa.JSON, nullable=False),
        sa.Column("rows", sa.JSON, nullable=False),
        sa.Column("split_assignments", sa.JSON, nullable=False),
        sa.Column("split_report", sa.JSON, nullable=False),
        sa.Column("leakage_report", sa.JSON, nullable=False),
        sa.Column("blocked_reasons", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "source_manifest_id",
            "feature_set_id",
            "label_set_id",
            name="uq_training_dataset_snapshot_contract",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_training_dataset_snapshot_idempotency"),
    )
    op.create_index(
        "ix_training_dataset_snapshots_source_manifest_id",
        "training_dataset_snapshots",
        ["source_manifest_id"],
    )
    op.create_table(
        "model_releases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(320), nullable=False),
        sa.Column("model_version", sa.String(100), unique=True, nullable=False),
        sa.Column("algorithm", sa.String(48), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "feature_set_id",
            sa.String(36),
            sa.ForeignKey("learning_feature_sets.id"),
            nullable=False,
        ),
        sa.Column(
            "label_set_id", sa.String(36), sa.ForeignKey("learning_label_sets.id"), nullable=False
        ),
        sa.Column(
            "dataset_snapshot_id",
            sa.String(36),
            sa.ForeignKey("training_dataset_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "predecessor_id", sa.String(36), sa.ForeignKey("model_releases.id"), nullable=True
        ),
        sa.Column("artifact", sa.JSON, nullable=False),
        sa.Column("evaluation", sa.JSON, nullable=False),
        sa.Column("training_report", sa.JSON, nullable=False),
        sa.Column("model_card", sa.JSON, nullable=False),
        sa.Column("approval_required", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inactive_reason", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_model_release_idempotency"),
    )
    op.create_index("ix_model_releases_status", "model_releases", ["status"])
    op.create_table(
        "model_replay_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(320), nullable=False),
        sa.Column(
            "model_release_id", sa.String(36), sa.ForeignKey("model_releases.id"), nullable=False
        ),
        sa.Column(
            "dataset_snapshot_id",
            sa.String(36),
            sa.ForeignKey("training_dataset_snapshots.id"),
            nullable=False,
        ),
        sa.Column("metrics", sa.JSON, nullable=False),
        sa.Column("accuracy_claim_allowed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_model_replay_idempotency"),
    )
    op.create_table(
        "model_drift_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(320), nullable=False),
        sa.Column(
            "model_release_id", sa.String(36), sa.ForeignKey("model_releases.id"), nullable=True
        ),
        sa.Column(
            "baseline_snapshot_id",
            sa.String(36),
            sa.ForeignKey("training_dataset_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "comparison_snapshot_id",
            sa.String(36),
            sa.ForeignKey("training_dataset_snapshots.id"),
            nullable=False,
        ),
        sa.Column("feature_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("threshold", sa.Float, nullable=False, server_default="0.2"),
        sa.Column("metrics", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_model_drift_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("model_drift_reports")
    op.drop_table("model_replay_runs")
    op.drop_index("ix_model_releases_status", table_name="model_releases")
    op.drop_table("model_releases")
    op.drop_index(
        "ix_training_dataset_snapshots_source_manifest_id",
        table_name="training_dataset_snapshots",
    )
    op.drop_table("training_dataset_snapshots")
    op.drop_table("learning_label_sets")
    op.drop_table("learning_feature_sets")
