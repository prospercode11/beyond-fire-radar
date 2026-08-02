"""add tamper-evident audit chaining and session lifecycle fields"""

import hashlib
import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0019_phase10_hardening"
down_revision = "0018_learning_control_actions"
branch_labels = None
depends_on = None


def _aware_iso(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _digest(row: dict[str, object], previous_hash: str, sequence: int) -> str:
    metadata = row["event_metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    payload = {
        "id": row["id"],
        "actor_user_id": row["actor_user_id"],
        "action": row["action"],
        "resource_type": row["resource_type"],
        "resource_id": row["resource_id"],
        "request_id": row["request_id"],
        "metadata": metadata,
        "sequence": sequence,
        "previous_hash": previous_hash,
        "created_at": _aware_iso(row["created_at"]),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column("sessions", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sessions", sa.Column("replaced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_sessions_last_used_at", "sessions", ["last_used_at"])

    op.add_column("audit_events", sa.Column("sequence", sa.Integer(), nullable=True))
    op.add_column("audit_events", sa.Column("previous_hash", sa.String(64), nullable=True))
    op.add_column("audit_events", sa.Column("event_hash", sa.String(64), nullable=True))
    op.create_table(
        "audit_chain_heads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    connection = op.get_bind()
    rows = [
        dict(row)
        for row in connection.execute(
            sa.text(
                "SELECT id, actor_user_id, action, resource_type, resource_id, request_id, "
                "event_metadata, created_at FROM audit_events ORDER BY created_at, id"
            )
        ).mappings()
    ]
    previous_hash = ""
    for sequence, row in enumerate(rows, start=1):
        event_hash = _digest(row, previous_hash, sequence)
        connection.execute(
            sa.text(
                "UPDATE audit_events SET sequence=:sequence, previous_hash=:previous_hash, "
                "event_hash=:event_hash WHERE id=:id"
            ),
            {
                "sequence": sequence,
                "previous_hash": previous_hash,
                "event_hash": event_hash,
                "id": row["id"],
            },
        )
        previous_hash = event_hash
    connection.execute(
        sa.text(
            "INSERT INTO audit_chain_heads (id, last_sequence, last_hash) "
            "VALUES (1, :last_sequence, :last_hash)"
        ),
        {"last_sequence": len(rows), "last_hash": previous_hash},
    )
    with op.batch_alter_table("audit_events", recreate="always") as batch_op:
        batch_op.alter_column("sequence", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("previous_hash", existing_type=sa.String(64), nullable=False)
        batch_op.alter_column("event_hash", existing_type=sa.String(64), nullable=False)
        batch_op.create_unique_constraint("uq_audit_events_sequence", ["sequence"])
        batch_op.create_index("ix_audit_events_event_hash", ["event_hash"])


def downgrade() -> None:
    with op.batch_alter_table("audit_events", recreate="always") as batch_op:
        batch_op.drop_index("ix_audit_events_event_hash")
        batch_op.drop_constraint("uq_audit_events_sequence", type_="unique")
        batch_op.drop_column("event_hash")
        batch_op.drop_column("previous_hash")
        batch_op.drop_column("sequence")
    op.drop_table("audit_chain_heads")
    op.drop_index("ix_sessions_last_used_at", table_name="sessions")
    op.drop_column("sessions", "replaced_at")
    op.drop_column("sessions", "last_used_at")
