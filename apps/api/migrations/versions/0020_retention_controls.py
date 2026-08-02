"""add raw-payload retention tombstones"""

import sqlalchemy as sa
from alembic import op

revision = "0020_retention_controls"
down_revision = "0019_phase10_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_snapshots",
        sa.Column("payload_purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_raw_snapshots_payload_purged_at", "raw_snapshots", ["payload_purged_at"])


def downgrade() -> None:
    op.drop_index("ix_raw_snapshots_payload_purged_at", table_name="raw_snapshots")
    op.drop_column("raw_snapshots", "payload_purged_at")
