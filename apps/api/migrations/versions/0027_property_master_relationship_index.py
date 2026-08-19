"""index active provider-scoped parcel relationship expansion"""

from alembic import op

revision = "0027_property_master_relationship_index"
down_revision = "0026_property_address_core_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_parcels_provider_active_master_parcel",
        "parcels",
        ["provider_id", "is_active", "master_parcel_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_parcels_provider_active_master_parcel", table_name="parcels")
