"""scope source identity aliases to their provider

Revision ID: 0006_scope_incident_aliases_by_provider
Revises: 0005_incident_integrity_controls
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_scope_incident_aliases_by_provider"
down_revision = "0005_incident_integrity_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("incident_aliases", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("provider_id", sa.String(100), nullable=True))
        batch_op.create_foreign_key(
            "fk_incident_aliases_provider_id", "providers", ["provider_id"], ["id"]
        )
    op.execute(
        """
        UPDATE incident_aliases
        SET provider_id = (
            SELECT provider_id FROM canonical_incidents
            WHERE canonical_incidents.id = incident_aliases.incident_id
        )
        """
    )
    with op.batch_alter_table("incident_aliases", recreate="always") as batch_op:
        batch_op.alter_column(
            "provider_id",
            existing_type=sa.String(100),
            nullable=False,
        )
    inspector = sa.inspect(op.get_bind())
    index_names = {item["name"] for item in inspector.get_indexes("incident_aliases")}
    if "uq_incident_alias_source_record" in index_names:
        op.drop_index("uq_incident_alias_source_record", table_name="incident_aliases")
    if "ix_incident_aliases_alias_value" in index_names:
        op.drop_index("ix_incident_aliases_alias_value", table_name="incident_aliases")
    op.create_index(
        "uq_incident_alias_provider_source_record",
        "incident_aliases",
        ["provider_id", "alias_type", "alias_value"],
        unique=True,
        sqlite_where=sa.text("alias_type = 'source_record_id'"),
        postgresql_where=sa.text("alias_type = 'source_record_id'"),
    )


def downgrade() -> None:
    op.drop_index("uq_incident_alias_provider_source_record", table_name="incident_aliases")
    with op.batch_alter_table("incident_aliases", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_incident_aliases_provider_id", type_="foreignkey")
        batch_op.drop_column("provider_id")
    op.execute(
        """
        UPDATE incident_aliases
        SET alias_type = 'source_record_collision', collision = 1
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY alias_type, alias_value ORDER BY created_at, id
                ) AS row_number
                FROM incident_aliases
                WHERE alias_type = 'source_record_id'
            ) ranked
            WHERE row_number > 1
        )
        """
    )
    op.create_index(
        "uq_incident_alias_source_record",
        "incident_aliases",
        ["alias_type", "alias_value"],
        unique=True,
        sqlite_where=sa.text("alias_type = 'source_record_id'"),
        postgresql_where=sa.text("alias_type = 'source_record_id'"),
    )
    # Return the non-unique lookup index owned by revision 0005 so that its
    # downgrade can remove the index before dropping the revision.
    op.create_index(
        "ix_incident_aliases_alias_value",
        "incident_aliases",
        ["alias_type", "alias_value"],
        unique=False,
    )
