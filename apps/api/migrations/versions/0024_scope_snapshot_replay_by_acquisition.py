"""retain separate provenance when identical bytes arrive through manual and live paths"""

import sqlalchemy as sa
from alembic import op

revision = "0024_scope_snapshot_replay_by_acquisition"
down_revision = "0023_sarasota_polling_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("raw_snapshots", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "acquisition_mode",
                sa.String(32),
                nullable=False,
                server_default="manual_snapshot",
            )
        )
        batch_op.drop_constraint("uq_raw_snapshots_content_hash", type_="unique")
        batch_op.create_unique_constraint(
            "uq_raw_snapshots_provider_hash_mode",
            ["provider_id", "content_hash", "acquisition_mode"],
        )


def downgrade() -> None:
    with op.batch_alter_table("raw_snapshots", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_raw_snapshots_provider_hash_mode", type_="unique")
        batch_op.drop_column("acquisition_mode")
        batch_op.create_unique_constraint("uq_raw_snapshots_content_hash", ["content_hash"])
