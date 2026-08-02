from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditChainHead, AuditEvent


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _event_digest(
    *,
    event_id: str,
    actor_user_id: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    request_id: str,
    metadata: Dict[str, Any],
    sequence: int,
    previous_hash: str,
    created_at: datetime,
) -> str:
    payload = {
        "id": event_id,
        "actor_user_id": actor_user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "request_id": request_id,
        "metadata": metadata,
        "sequence": sequence,
        "previous_hash": previous_hash,
        "created_at": _aware(created_at).isoformat(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def record_audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    actor_user_id: Optional[str],
    request_id: str,
    resource_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    event_id = str(uuid4())
    event_metadata = metadata or {}
    created_at = datetime.now(timezone.utc)
    head = db.scalar(select(AuditChainHead).where(AuditChainHead.id == 1).with_for_update())
    if head is None:
        head = AuditChainHead(id=1, last_sequence=0, last_hash="", updated_at=created_at)
        db.add(head)
        db.flush()

    sequence = head.last_sequence + 1
    event_hash = _event_digest(
        event_id=event_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        metadata=event_metadata,
        sequence=sequence,
        previous_hash=head.last_hash,
        created_at=created_at,
    )
    event = AuditEvent(
        id=event_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        event_metadata=event_metadata,
        sequence=sequence,
        previous_hash=head.last_hash,
        event_hash=event_hash,
        created_at=created_at,
    )
    head.last_sequence = sequence
    head.last_hash = event_hash
    head.updated_at = created_at
    db.add(event)
    db.flush()
    return event


@dataclass(frozen=True)
class AuditIntegrityResult:
    valid: bool
    event_count: int
    first_invalid_sequence: Optional[int]
    reason: Optional[str]


def verify_audit_chain(db: Session) -> AuditIntegrityResult:
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.sequence, AuditEvent.id)).all()
    previous_hash = ""
    expected_sequence = 1
    for event in events:
        if event.sequence != expected_sequence:
            return AuditIntegrityResult(
                valid=False,
                event_count=len(events),
                first_invalid_sequence=event.sequence,
                reason="audit sequence contains a gap or duplicate",
            )
        if event.previous_hash != previous_hash:
            return AuditIntegrityResult(
                valid=False,
                event_count=len(events),
                first_invalid_sequence=event.sequence,
                reason="audit previous hash does not match the preceding event",
            )
        expected_hash = _event_digest(
            event_id=event.id,
            actor_user_id=event.actor_user_id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            request_id=event.request_id,
            metadata=event.event_metadata,
            sequence=event.sequence,
            previous_hash=event.previous_hash,
            created_at=event.created_at,
        )
        if event.event_hash != expected_hash:
            return AuditIntegrityResult(
                valid=False,
                event_count=len(events),
                first_invalid_sequence=event.sequence,
                reason="audit event hash mismatch",
            )
        previous_hash = event.event_hash
        expected_sequence += 1
    head = db.scalar(select(AuditChainHead).where(AuditChainHead.id == 1))
    if head is not None and (head.last_sequence != len(events) or head.last_hash != previous_hash):
        return AuditIntegrityResult(
            valid=False,
            event_count=len(events),
            first_invalid_sequence=None,
            reason="audit chain head does not match the event chain",
        )
    return AuditIntegrityResult(
        valid=True,
        event_count=len(events),
        first_invalid_sequence=None,
        reason=None,
    )
