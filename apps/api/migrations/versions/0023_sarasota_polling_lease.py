"""add a provider-scoped lease for the Sarasota polling worker"""

import sqlalchemy as sa
from alembic import op

revision = "0023_sarasota_polling_lease"
down_revision = "0022_raw_purge_pending_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_poll_leases",
        sa.Column(
            "provider_id",
            sa.String(100),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("lease_owner", sa.String(120), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(40), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_poll_leases")
