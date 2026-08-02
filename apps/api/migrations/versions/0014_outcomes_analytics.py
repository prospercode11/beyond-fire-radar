"""add immutable outcome labels, outcome events, and reproducible analytics runs"""

import sqlalchemy as sa
from alembic import op

revision = "0014_outcomes_analytics"
down_revision = "0013_workflow_state_guards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outcome_labels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column(
            "score_run_id", sa.String(36), sa.ForeignKey("opportunity_score_runs.id"), nullable=True
        ),
        sa.Column("label_type", sa.String(48), nullable=False),
        sa.Column("label_value", sa.String(64), nullable=False),
        sa.Column("error_category", sa.String(48), nullable=True),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("provenance", sa.JSON, nullable=False),
        sa.Column("idempotency_key", sa.String(320), nullable=False),
        sa.Column("reviewer_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_outcome_label_idempotency"),
    )
    op.create_index("ix_outcome_labels_incident_id", "outcome_labels", ["incident_id"])
    op.create_index("ix_outcome_labels_score_run_id", "outcome_labels", ["score_run_id"])
    op.create_index(
        "ix_outcome_labels_incident_type",
        "outcome_labels",
        ["incident_id", "label_type", "created_at"],
    )

    op.create_table(
        "incident_outcome_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column(
            "score_run_id", sa.String(36), sa.ForeignKey("opportunity_score_runs.id"), nullable=True
        ),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(40), nullable=False, server_default="manual_internal"),
        sa.Column("details", sa.JSON, nullable=False),
        sa.Column("idempotency_key", sa.String(320), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_incident_outcome_event_idempotency"),
    )
    op.create_index(
        "ix_incident_outcome_events_incident_id", "incident_outcome_events", ["incident_id"]
    )
    op.create_index(
        "ix_incident_outcome_events_score_run_id", "incident_outcome_events", ["score_run_id"]
    )
    op.create_index(
        "ix_incident_outcome_events_incident_occurred",
        "incident_outcome_events",
        ["incident_id", "occurred_at"],
    )

    op.create_table(
        "evaluation_manifests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manifest_type", sa.String(48), nullable=False),
        sa.Column("manifest_version", sa.String(48), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filters", sa.JSON, nullable=False),
        sa.Column("incident_ids", sa.JSON, nullable=False),
        sa.Column("score_run_ids", sa.JSON, nullable=False),
        sa.Column("label_ids", sa.JSON, nullable=False),
        sa.Column("outcome_event_ids", sa.JSON, nullable=False),
        sa.Column("source_acquisition_modes", sa.JSON, nullable=False),
        sa.Column("claim_status", sa.String(40), nullable=False, server_default="directional_only"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "analytics_metrics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "manifest_id", sa.String(36), sa.ForeignKey("evaluation_manifests.id"), nullable=False
        ),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("metric_version", sa.String(48), nullable=False),
        sa.Column("numerator", sa.Float, nullable=True),
        sa.Column("denominator", sa.Integer, nullable=False, server_default="0"),
        sa.Column("value", sa.Float, nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("warning", sa.Text, nullable=True),
        sa.Column("details", sa.JSON, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("manifest_id", "metric_name", name="uq_analytics_metric_manifest_name"),
    )
    op.create_index("ix_analytics_metrics_manifest_id", "analytics_metrics", ["manifest_id"])


def downgrade() -> None:
    op.drop_index("ix_analytics_metrics_manifest_id", table_name="analytics_metrics")
    op.drop_table("analytics_metrics")
    op.drop_table("evaluation_manifests")
    op.drop_index(
        "ix_incident_outcome_events_incident_occurred", table_name="incident_outcome_events"
    )
    op.drop_index("ix_incident_outcome_events_score_run_id", table_name="incident_outcome_events")
    op.drop_index("ix_incident_outcome_events_incident_id", table_name="incident_outcome_events")
    op.drop_table("incident_outcome_events")
    op.drop_index("ix_outcome_labels_incident_type", table_name="outcome_labels")
    op.drop_index("ix_outcome_labels_score_run_id", table_name="outcome_labels")
    op.drop_index("ix_outcome_labels_incident_id", table_name="outcome_labels")
    op.drop_table("outcome_labels")
