"""bind outcome labels to reviewed predictions and persist source/taxonomy provenance"""

import sqlalchemy as sa
from alembic import op

revision = "0015_outcome_integrity"
down_revision = "0014_outcomes_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("outcome_labels", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "property_match_run_id",
                sa.String(36),
                sa.ForeignKey(
                    "incident_property_match_runs.id", name="fk_outcome_labels_match_run"
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "property_candidate_id",
                sa.String(36),
                sa.ForeignKey(
                    "incident_property_candidates.id", name="fk_outcome_labels_candidate"
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "property_decision_id",
                sa.String(36),
                sa.ForeignKey("property_match_decisions.id", name="fk_outcome_labels_decision"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "taxonomy_version",
                sa.String(48),
                nullable=False,
                server_default="outcomes-taxonomy.v1",
            )
        )
        batch_op.create_check_constraint(
            "ck_outcome_labels_taxonomy",
            sa.text(
                "label_type IN ('review_relevance', 'classification', 'property_match', 'alert_usefulness', 'client_status') AND (error_category IS NULL OR error_category IN ('source_quality', 'incident_classification', 'incident_linkage', 'property_match', 'opportunity_ranking', 'workflow', 'other'))"
            ),
        )

    with op.batch_alter_table("incident_outcome_events", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "taxonomy_version",
                sa.String(48),
                nullable=False,
                server_default="outcomes-taxonomy.v1",
            )
        )
        batch_op.create_check_constraint(
            "ck_incident_outcome_events_taxonomy",
            sa.text(
                "event_type IN ('review_started', 'review_completed', 'alert_acknowledged', 'property_reviewed', 'found_first', 'existing_client_confirmed', 'not_relevant', 'closed') AND source = 'manual_internal'"
            ),
        )

    with op.batch_alter_table("evaluation_manifests", recreate="always") as batch_op:
        for name in (
            "source_retrieval_ids",
            "source_provider_ids",
            "source_authorization_bases",
            "source_snapshot_hashes",
        ):
            batch_op.add_column(
                sa.Column(name, sa.JSON, nullable=False, server_default=sa.text("'[]'"))
            )
        batch_op.add_column(
            sa.Column("source_provenance", sa.JSON, nullable=False, server_default=sa.text("'{}'"))
        )


def downgrade() -> None:
    with op.batch_alter_table("evaluation_manifests", recreate="always") as batch_op:
        batch_op.drop_column("source_provenance")
        batch_op.drop_column("source_snapshot_hashes")
        batch_op.drop_column("source_authorization_bases")
        batch_op.drop_column("source_provider_ids")
        batch_op.drop_column("source_retrieval_ids")
    with op.batch_alter_table("incident_outcome_events", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_incident_outcome_events_taxonomy", type_="check")
        batch_op.drop_column("taxonomy_version")
    with op.batch_alter_table("outcome_labels", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_outcome_labels_taxonomy", type_="check")
        batch_op.drop_column("taxonomy_version")
        batch_op.drop_column("property_decision_id")
        batch_op.drop_column("property_candidate_id")
        batch_op.drop_column("property_match_run_id")
