"""add incident integrity controls, signal history, and responder tables

Revision ID: 0005_incident_integrity_controls
Revises: 0004_incident_intelligence
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_incident_integrity_controls"
down_revision = "0004_incident_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("provider_retrievals", recreate="always") as batch_op:
        batch_op.alter_column(
            "acquisition_mode",
            existing_type=sa.String(32),
            server_default=None,
        )

    with op.batch_alter_table("canonical_incidents", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "review_signal_status", sa.String(24), nullable=False, server_default="not_issued"
            )
        )
        batch_op.add_column(
            sa.Column("review_signal_issued_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("review_signal_revoked_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("review_signal_revocation_reason", sa.Text(), nullable=True))

    with op.batch_alter_table("incident_observation_links", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("assignment_key", sa.String(36), nullable=True))

    # 0004 did not yet have a database-level current-assignment guard. Retain the oldest
    # assignment as current and keep later competing rows as historical evidence before adding
    # the unique index.
    op.execute(
        """
        UPDATE incident_observation_links
        SET is_current = 0
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY observation_id ORDER BY created_at, id
                ) AS row_number
                FROM incident_observation_links
                WHERE is_current = 1
            ) ranked
            WHERE row_number > 1
        )
        """
    )
    op.execute(
        "UPDATE incident_observation_links SET assignment_key = observation_id WHERE is_current = 1"
    )
    op.create_index(
        "uq_current_incident_observation_assignment",
        "incident_observation_links",
        ["assignment_key"],
        unique=True,
    )
    op.create_index(
        "ix_incident_aliases_alias_value",
        "incident_aliases",
        ["alias_type", "alias_value"],
        unique=False,
    )

    op.create_table(
        "responding_agencies",
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
        sa.Column("agency", sa.String(120), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "incident_id", "agency", "observation_id", name="uq_incident_agency_observation"
        ),
    )
    op.create_index("ix_responding_agencies_incident_id", "responding_agencies", ["incident_id"])
    op.create_index(
        "ix_responding_agencies_observation_id", "responding_agencies", ["observation_id"]
    )

    op.create_table(
        "responding_stations",
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
        sa.Column("station", sa.String(200), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "incident_id", "station", "observation_id", name="uq_incident_station_observation"
        ),
    )
    op.create_index("ix_responding_stations_incident_id", "responding_stations", ["incident_id"])
    op.create_index(
        "ix_responding_stations_observation_id", "responding_stations", ["observation_id"]
    )

    op.create_table(
        "incident_dispositions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column(
            "observation_id",
            sa.String(36),
            sa.ForeignKey("dispatch_observations.id"),
            nullable=True,
        ),
        sa.Column("disposition", sa.String(120), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index(
        "ix_incident_dispositions_incident_id", "incident_dispositions", ["incident_id"]
    )
    op.create_index(
        "ix_incident_dispositions_observation_id", "incident_dispositions", ["observation_id"]
    )


def downgrade() -> None:
    op.drop_table("incident_dispositions")
    op.drop_table("responding_stations")
    op.drop_table("responding_agencies")
    op.drop_index("ix_incident_aliases_alias_value", table_name="incident_aliases")
    op.drop_index(
        "uq_current_incident_observation_assignment", table_name="incident_observation_links"
    )
    with op.batch_alter_table("incident_observation_links", recreate="always") as batch_op:
        batch_op.drop_column("assignment_key")
    with op.batch_alter_table("canonical_incidents", recreate="always") as batch_op:
        batch_op.drop_column("review_signal_revocation_reason")
        batch_op.drop_column("review_signal_revoked_at")
        batch_op.drop_column("review_signal_issued_at")
        batch_op.drop_column("review_signal_status")
    with op.batch_alter_table("provider_retrievals", recreate="always") as batch_op:
        batch_op.alter_column(
            "acquisition_mode",
            existing_type=sa.String(32),
            server_default="manual_snapshot",
        )
