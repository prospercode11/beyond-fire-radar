"""index exact property address and alias lookups by active provider scope"""

from alembic import op

revision = "0025_property_exact_address_indexes"
down_revision = "0024_scope_snapshot_replay_by_acquisition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_parcels_provider_active_normalized_address",
        "parcels",
        ["provider_id", "is_active", "normalized_address"],
    )
    op.create_index(
        "ix_parcel_address_aliases_normalized_address_parcel_id",
        "parcel_address_aliases",
        ["normalized_address", "parcel_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_parcel_address_aliases_normalized_address_parcel_id",
        table_name="parcel_address_aliases",
    )
    op.drop_index("ix_parcels_provider_active_normalized_address", table_name="parcels")
