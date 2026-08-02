"""add failure-safe pending state to dispatch raw snapshots"""

import sqlalchemy as sa
from alembic import op

revision = "0022_raw_purge_pending_state"
down_revision = "0021_property_retention_and_purge_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_snapshots",
        sa.Column("payload_purge_pending_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_raw_snapshots_payload_purge_pending_at",
        "raw_snapshots",
        ["payload_purge_pending_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_raw_snapshots_payload_purge_pending_at", table_name="raw_snapshots")
    op.drop_column("raw_snapshots", "payload_purge_pending_at")
