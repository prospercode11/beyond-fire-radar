"""bind alert usefulness labels and retain property-source provenance"""

import sqlalchemy as sa
from alembic import op

revision = "0016_outcome_alert_provenance"
down_revision = "0015_outcome_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("outcome_labels", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "alert_id",
                sa.String(36),
                sa.ForeignKey("internal_alerts.id", name="fk_outcome_labels_alert"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_outcome_labels_alert_id", ["alert_id"], unique=False)

    with op.batch_alter_table("evaluation_manifests", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_property_import_ids",
                sa.JSON,
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("evaluation_manifests", recreate="always") as batch_op:
        batch_op.drop_column("source_property_import_ids")
    with op.batch_alter_table("outcome_labels", recreate="always") as batch_op:
        batch_op.drop_index("ix_outcome_labels_alert_id")
        batch_op.drop_column("alert_id")
