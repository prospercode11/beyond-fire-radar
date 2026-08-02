"""record incident-link assignment end times for temporal scoring"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0011_temporal_incident_links"
down_revision = "0010_scoring_asof_predecessor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "incident_observation_links",
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    bind = op.get_bind()
    metadata = sa.MetaData()
    links = sa.Table("incident_observation_links", metadata, autoload_with=bind)
    merges = sa.Table("incident_merges", metadata, autoload_with=bind)
    splits = sa.Table("incident_splits", metadata, autoload_with=bind)
    for link in bind.execute(
        sa.select(links).where(links.c.is_current.is_(False), links.c.ended_at.is_(None))
    ).mappings():
        end_times = list(
            bind.execute(
                sa.select(merges.c.created_at).where(
                    merges.c.absorbed_incident_id == link["incident_id"]
                )
            ).scalars()
        )
        for split in bind.execute(
            sa.select(splits.c.created_at, splits.c.moved_observation_ids).where(
                splits.c.original_incident_id == link["incident_id"]
            )
        ).mappings():
            moved_ids = split["moved_observation_ids"]
            if isinstance(moved_ids, str):
                moved_ids = json.loads(moved_ids)
            if link["observation_id"] in moved_ids:
                end_times.append(split["created_at"])
        if end_times:
            bind.execute(
                links.update().where(links.c.id == link["id"]).values(ended_at=min(end_times))
            )


def downgrade() -> None:
    op.drop_column("incident_observation_links", "ended_at")
