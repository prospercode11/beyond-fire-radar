from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import AuditEvent


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
    event = AuditEvent(
        id=str(uuid4()),
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        event_metadata=metadata or {},
    )
    db.add(event)
    db.flush()
    return event
