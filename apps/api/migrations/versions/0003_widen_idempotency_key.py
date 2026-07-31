"""widen provider-scoped idempotency key storage

Revision ID: 0003_widen_idempotency_key
Revises: 0002_dispatch_ingestion
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_widen_idempotency_key"
down_revision = "0002_dispatch_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("import_jobs", recreate="always") as batch_op:
        batch_op.alter_column("idempotency_key", existing_type=sa.String(200), type_=sa.String(320))


def downgrade() -> None:
    with op.batch_alter_table("import_jobs", recreate="always") as batch_op:
        batch_op.alter_column("idempotency_key", existing_type=sa.String(320), type_=sa.String(200))
