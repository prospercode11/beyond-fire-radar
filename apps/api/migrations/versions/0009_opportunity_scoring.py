"""add transparent opportunity scoring history and feature provenance"""

import sqlalchemy as sa
from alembic import op

revision = "0009_opportunity_scoring"
down_revision = "0008_property_current_import"
branch_labels = None
depends_on = None


def _json() -> sa.JSON:
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "scoring_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("component_versions", _json(), nullable=False),
        sa.Column("priors", _json(), nullable=False),
        sa.Column("rules", _json(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "opportunity_score_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column(
            "property_match_run_id",
            sa.String(36),
            sa.ForeignKey("incident_property_match_runs.id"),
            nullable=True,
        ),
        sa.Column(
            "property_provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=True
        ),
        sa.Column("scoring_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provisional_score", sa.Float(), nullable=True),
        sa.Column("evidence_tier", sa.String(32), nullable=False),
        sa.Column("alert_eligibility", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("abstention_reason", sa.Text(), nullable=True),
        sa.Column("hard_gate_status", sa.String(32), nullable=False),
        sa.Column("explanation", _json(), nullable=False),
        sa.Column("source_observation_ids", _json(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_opportunity_score_runs_incident_id", "opportunity_score_runs", ["incident_id"]
    )
    op.create_index(
        "ix_opportunity_score_runs_property_provider_id",
        "opportunity_score_runs",
        ["property_provider_id"],
    )
    op.create_index(
        "ix_opportunity_score_runs_is_current", "opportunity_score_runs", ["is_current"]
    )
    op.create_index(
        "uq_opportunity_score_current_incident",
        "opportunity_score_runs",
        ["incident_id"],
        unique=True,
        sqlite_where=sa.text("is_current = 1"),
        postgresql_where=sa.text("is_current = true"),
    )

    op.create_table(
        "opportunity_score_features",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "score_run_id",
            sa.String(36),
            sa.ForeignKey("opportunity_score_runs.id"),
            nullable=False,
        ),
        sa.Column("feature_name", sa.String(100), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("contribution", sa.Float(), nullable=True),
        sa.Column("evidence", _json(), nullable=False),
        sa.Column("source_observation_ids", _json(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feature_version", sa.String(80), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "score_run_id", "feature_name", name="uq_opportunity_score_feature_name"
        ),
    )
    op.create_index(
        "ix_opportunity_score_features_score_run_id",
        "opportunity_score_features",
        ["score_run_id"],
    )

    op.create_table(
        "opportunity_score_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column(
            "score_run_id", sa.String(36), sa.ForeignKey("opportunity_score_runs.id"), nullable=True
        ),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_opportunity_score_overrides_incident_id",
        "opportunity_score_overrides",
        ["incident_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opportunity_score_overrides_incident_id", table_name="opportunity_score_overrides"
    )
    op.drop_table("opportunity_score_overrides")
    op.drop_index(
        "ix_opportunity_score_features_score_run_id", table_name="opportunity_score_features"
    )
    op.drop_table("opportunity_score_features")
    op.drop_index("uq_opportunity_score_current_incident", table_name="opportunity_score_runs")
    op.drop_index("ix_opportunity_score_runs_is_current", table_name="opportunity_score_runs")
    op.drop_index(
        "ix_opportunity_score_runs_property_provider_id", table_name="opportunity_score_runs"
    )
    op.drop_index("ix_opportunity_score_runs_incident_id", table_name="opportunity_score_runs")
    op.drop_table("opportunity_score_runs")
    op.drop_table("scoring_versions")
