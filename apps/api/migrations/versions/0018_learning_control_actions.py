"""add idempotent model controls and release state guards"""

import sqlalchemy as sa
from alembic import op

revision = "0018_learning_control_actions"
down_revision = "0017_learning_infrastructure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("model_releases", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_model_release_status",
            "status in ('blocked', 'inactive', 'candidate', 'challenger', 'champion', 'retired', 'rolled_back')",
        )
    op.create_index(
        "uq_model_releases_one_champion",
        "model_releases",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status = 'champion'"),
        postgresql_where=sa.text("status = 'champion'"),
    )
    op.create_table(
        "model_control_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(320), unique=True, nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column(
            "model_release_id",
            sa.String(36),
            sa.ForeignKey("model_releases.id"),
            nullable=False,
        ),
        sa.Column(
            "result_model_release_id",
            sa.String(36),
            sa.ForeignKey("model_releases.id"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_model_control_actions_model_release_id",
        "model_control_actions",
        ["model_release_id"],
    )
    op.create_index(
        "ix_model_control_actions_result_model_release_id",
        "model_control_actions",
        ["result_model_release_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_control_actions_result_model_release_id", table_name="model_control_actions"
    )
    op.drop_index("ix_model_control_actions_model_release_id", table_name="model_control_actions")
    op.drop_table("model_control_actions")
    op.drop_index("uq_model_releases_one_champion", table_name="model_releases")
    with op.batch_alter_table("model_releases", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_model_release_status", type_="check")
