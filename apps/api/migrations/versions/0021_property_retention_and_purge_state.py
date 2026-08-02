"""extend retention tombstones to property imports and failure-safe purge state"""

import sqlalchemy as sa
from alembic import op

revision = "0021_property_retention_and_purge_state"
down_revision = "0020_retention_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "property_imports",
        sa.Column("payload_purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "property_imports",
        sa.Column("payload_purge_pending_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_property_imports_payload_purged_at", "property_imports", ["payload_purged_at"]
    )
    op.create_index(
        "ix_property_imports_payload_purge_pending_at",
        "property_imports",
        ["payload_purge_pending_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_property_imports_payload_purge_pending_at", table_name="property_imports")
    op.drop_index("ix_property_imports_payload_purged_at", table_name="property_imports")
    op.drop_column("property_imports", "payload_purge_pending_at")
    op.drop_column("property_imports", "payload_purged_at")
