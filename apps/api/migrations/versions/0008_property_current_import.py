"""enforce one current property import per provider"""

import sqlalchemy as sa
from alembic import op

revision = "0008_property_current_import"
down_revision = "0007_property_resolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_property_import_current_provider",
        "property_imports",
        ["provider_id"],
        unique=True,
        sqlite_where=sa.text("is_current = 1"),
        postgresql_where=sa.text("is_current = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_property_import_current_provider", table_name="property_imports")
