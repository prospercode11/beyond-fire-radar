from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.dependencies import AdminUser, DbSession
from app.models import AuditEvent
from app.schemas import AuditResponse

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/audit", response_model=list[AuditResponse])
def audit_events(user: AdminUser, db: DbSession) -> list[AuditResponse]:
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(100)).all()
    return [
        AuditResponse(
            id=event.id,
            actor_user_id=event.actor_user_id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            request_id=event.request_id,
            metadata=event.event_metadata,
            created_at=event.created_at,
        )
        for event in events
    ]
