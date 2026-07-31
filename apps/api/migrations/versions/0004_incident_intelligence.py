"""add canonical incident intelligence and manual-source provenance

Revision ID: 0004_incident_intelligence
Revises: 0003_widen_idempotency_key
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_incident_intelligence"
down_revision = "0003_widen_idempotency_key"
branch_labels = None
depends_on = None


def _json() -> sa.JSON:
    return sa.JSON()


def upgrade() -> None:
    op.add_column(
        "provider_retrievals",
        sa.Column(
            "acquisition_mode", sa.String(32), nullable=False, server_default="manual_snapshot"
        ),
    )
    op.add_column(
        "provider_retrievals",
        sa.Column("authorization_basis", sa.String(80), nullable=True),
    )

    op.create_table(
        "canonical_incidents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("classification_family", sa.String(100), nullable=False),
        sa.Column("classification_version", sa.String(80), nullable=False),
        sa.Column("classification_confidence", sa.Float(), nullable=False),
        sa.Column("confidence_band", sa.String(32), nullable=False),
        sa.Column("review_band", sa.String(32), nullable=False),
        sa.Column("canonical_event_type", sa.String(200), nullable=True),
        sa.Column("first_event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canonical_location", sa.Text(), nullable=True),
        sa.Column("canonical_grid", sa.String(50), nullable=True),
        sa.Column("canonical_agency", sa.String(120), nullable=True),
        sa.Column("canonical_station", sa.String(200), nullable=True),
        sa.Column("contradiction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("classification_explanation", _json(), nullable=False),
        sa.Column("current_explanation", _json(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "merged_into_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_canonical_incidents_provider_id", "canonical_incidents", ["provider_id"])
    op.create_index("ix_canonical_incidents_state", "canonical_incidents", ["state"])
    op.create_index(
        "ix_canonical_incidents_classification_family",
        "canonical_incidents",
        ["classification_family"],
    )
    op.create_index("ix_canonical_incidents_is_active", "canonical_incidents", ["is_active"])
    op.create_index(
        "ix_canonical_incidents_merged_into_id", "canonical_incidents", ["merged_into_id"]
    )

    op.create_table(
        "incident_observation_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column(
            "observation_id",
            sa.String(36),
            sa.ForeignKey("dispatch_observations.id"),
            nullable=False,
        ),
        sa.Column(
            "raw_dispatch_row_id",
            sa.String(36),
            sa.ForeignKey("raw_dispatch_rows.id"),
            nullable=False,
        ),
        sa.Column("link_type", sa.String(32), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("decision_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "incident_id",
            "observation_id",
            "is_current",
            name="uq_incident_observation_link_version",
        ),
    )
    op.create_index(
        "ix_incident_observation_links_incident_id", "incident_observation_links", ["incident_id"]
    )
    op.create_index(
        "ix_incident_observation_links_observation_id",
        "incident_observation_links",
        ["observation_id"],
    )
    op.create_index(
        "ix_incident_observation_links_raw_dispatch_row_id",
        "incident_observation_links",
        ["raw_dispatch_row_id"],
    )
    op.create_index(
        "ix_incident_observation_links_is_current", "incident_observation_links", ["is_current"]
    )

    op.create_table(
        "incident_aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column(
            "observation_id",
            sa.String(36),
            sa.ForeignKey("dispatch_observations.id"),
            nullable=False,
        ),
        sa.Column("alias_type", sa.String(40), nullable=False),
        sa.Column("alias_value", sa.String(200), nullable=False),
        sa.Column("collision", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_incident_aliases_incident_id", "incident_aliases", ["incident_id"])
    op.create_index("ix_incident_aliases_observation_id", "incident_aliases", ["observation_id"])

    op.create_table(
        "incident_match_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "observation_id",
            sa.String(36),
            sa.ForeignKey("dispatch_observations.id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_incident_id",
            sa.String(36),
            sa.ForeignKey("canonical_incidents.id"),
            nullable=True,
        ),
        sa.Column(
            "reference_observation_id",
            sa.String(36),
            sa.ForeignKey("dispatch_observations.id"),
            nullable=True,
        ),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence_band", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("features", _json(), nullable=False),
        sa.Column("explanation", _json(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_incident_match_decisions_observation_id", "incident_match_decisions", ["observation_id"]
    )
    op.create_index(
        "ix_incident_match_decisions_candidate_incident_id",
        "incident_match_decisions",
        ["candidate_incident_id"],
    )

    op.create_table(
        "incident_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column(
            "observation_id",
            sa.String(36),
            sa.ForeignKey("dispatch_observations.id"),
            nullable=False,
        ),
        sa.Column("evidence_type", sa.String(24), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", _json(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_incident_evidence_incident_id", "incident_evidence", ["incident_id"])
    op.create_index("ix_incident_evidence_observation_id", "incident_evidence", ["observation_id"])

    op.create_table(
        "incident_timeline_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prior_state", sa.String(64), nullable=True),
        sa.Column("new_state", sa.String(64), nullable=True),
        sa.Column(
            "source_observation_id",
            sa.String(36),
            sa.ForeignKey("dispatch_observations.id"),
            nullable=True,
        ),
        sa.Column("details", _json(), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_incident_timeline_events_incident_id", "incident_timeline_events", ["incident_id"]
    )

    op.create_table(
        "incident_merges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "survivor_incident_id",
            sa.String(36),
            sa.ForeignKey("canonical_incidents.id"),
            nullable=False,
        ),
        sa.Column(
            "absorbed_incident_id",
            sa.String(36),
            sa.ForeignKey("canonical_incidents.id"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("explanation", _json(), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_incident_merges_survivor_incident_id", "incident_merges", ["survivor_incident_id"]
    )
    op.create_index(
        "ix_incident_merges_absorbed_incident_id", "incident_merges", ["absorbed_incident_id"]
    )

    op.create_table(
        "incident_splits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "original_incident_id",
            sa.String(36),
            sa.ForeignKey("canonical_incidents.id"),
            nullable=False,
        ),
        sa.Column(
            "new_incident_id",
            sa.String(36),
            sa.ForeignKey("canonical_incidents.id"),
            nullable=False,
        ),
        sa.Column("moved_observation_ids", _json(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("explanation", _json(), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_incident_splits_original_incident_id", "incident_splits", ["original_incident_id"]
    )
    op.create_index("ix_incident_splits_new_incident_id", "incident_splits", ["new_incident_id"])

    op.create_table(
        "incident_processing_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column(
            "retrieval_id", sa.String(36), sa.ForeignKey("provider_retrievals.id"), nullable=True
        ),
        sa.Column("acquisition_mode", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("linkage_version", sa.String(80), nullable=False),
        sa.Column("classification_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("linked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_incident_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contradiction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("retrieval_id", name="uq_incident_processing_retrieval"),
    )
    op.create_index(
        "ix_incident_processing_runs_provider_id", "incident_processing_runs", ["provider_id"]
    )
    op.create_index(
        "ix_incident_processing_runs_retrieval_id", "incident_processing_runs", ["retrieval_id"]
    )


def downgrade() -> None:
    for table in (
        "incident_processing_runs",
        "incident_splits",
        "incident_merges",
        "incident_timeline_events",
        "incident_evidence",
        "incident_match_decisions",
        "incident_aliases",
        "incident_observation_links",
        "canonical_incidents",
    ):
        op.drop_table(table)
    op.drop_column("provider_retrievals", "authorization_basis")
    op.drop_column("provider_retrievals", "acquisition_mode")
