"""index provider-scoped active property address components"""

from alembic import op

revision = "0026_property_address_core_index"
down_revision = "0025_property_exact_address_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_parcels_provider_active_address_core",
        "parcels",
        ["provider_id", "is_active", "house_number", "street_name", "street_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_parcels_provider_active_address_core", table_name="parcels")
