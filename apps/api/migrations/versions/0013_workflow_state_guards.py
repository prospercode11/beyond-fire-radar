"""add workflow escalation fields and internal-channel guard"""

import sqlalchemy as sa
from alembic import op

revision = "0013_workflow_state_guards"
down_revision = "0012_internal_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_alert_columns = {
        item["name"] for item in sa.inspect(bind).get_columns("internal_alerts")
    }
    if {"escalated_by", "escalated_at"} - existing_alert_columns:
        with op.batch_alter_table("internal_alerts", recreate="always") as batch_op:
            if "escalated_by" not in existing_alert_columns:
                batch_op.add_column(
                    sa.Column(
                        "escalated_by",
                        sa.String(36),
                        sa.ForeignKey("users.id", name="fk_internal_alerts_escalated_by_users"),
                        nullable=True,
                    )
                )
            if "escalated_at" not in existing_alert_columns:
                batch_op.add_column(
                    sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True)
                )
    existing_checks = {
        item["name"] for item in sa.inspect(bind).get_check_constraints("notification_jobs")
    }
    if "ck_notification_jobs_in_app" not in existing_checks:
        with op.batch_alter_table("notification_jobs", recreate="always") as batch_op:
            batch_op.create_check_constraint("ck_notification_jobs_in_app", "channel = 'in_app'")


def downgrade() -> None:
    bind = op.get_bind()
    existing_checks = {
        item["name"] for item in sa.inspect(bind).get_check_constraints("notification_jobs")
    }
    if "ck_notification_jobs_in_app" in existing_checks:
        with op.batch_alter_table("notification_jobs", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_notification_jobs_in_app", type_="check")
    existing_alert_columns = {
        item["name"] for item in sa.inspect(bind).get_columns("internal_alerts")
    }
    if {"escalated_by", "escalated_at"} <= existing_alert_columns:
        with op.batch_alter_table("internal_alerts", recreate="always") as batch_op:
            batch_op.drop_column("escalated_at")
            batch_op.drop_column("escalated_by")
