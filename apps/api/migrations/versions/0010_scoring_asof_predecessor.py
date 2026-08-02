"""bind scores to an as-of boundary and explicit predecessor"""

import sqlalchemy as sa
from alembic import op

revision = "0010_scoring_asof_predecessor"
down_revision = "0009_opportunity_scoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("opportunity_score_runs", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("previous_score_run_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_opportunity_score_previous",
            "opportunity_score_runs",
            ["previous_score_run_id"],
            ["id"],
        )
        batch_op.add_column(sa.Column("as_of", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE opportunity_score_runs SET as_of = COALESCE(completed_at, created_at) WHERE as_of IS NULL"
    )
    with op.batch_alter_table("opportunity_score_runs", recreate="always") as batch_op:
        batch_op.alter_column("as_of", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("opportunity_score_runs", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_opportunity_score_previous", type_="foreignkey")
        batch_op.drop_column("as_of")
        batch_op.drop_column("previous_score_run_id")
