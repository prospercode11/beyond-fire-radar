from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.audit import verify_audit_chain
from app.config import get_settings
from app.dependencies import AdminUser, DbSession
from app.models import AuditEvent, NotificationJob, ProviderHealth
from app.schemas import AuditIntegrityResponse, AuditResponse, OperationsStatusResponse

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
            sequence=event.sequence,
            previous_hash=event.previous_hash,
            event_hash=event.event_hash,
            created_at=event.created_at,
        )
        for event in events
    ]


@router.get("/audit/integrity", response_model=AuditIntegrityResponse)
def audit_integrity(user: AdminUser, db: DbSession) -> AuditIntegrityResponse:
    return AuditIntegrityResponse(**verify_audit_chain(db).__dict__)


@router.get("/operations", response_model=OperationsStatusResponse)
def operations_status(user: AdminUser, db: DbSession) -> OperationsStatusResponse:
    pending_query = select(NotificationJob).where(NotificationJob.status == "pending")
    pending = db.scalars(pending_query.order_by(NotificationJob.created_at).limit(1)).first()
    pending_count = (
        db.scalar(
            select(func.count())
            .select_from(NotificationJob)
            .where(NotificationJob.status == "pending")
        )
        or 0
    )
    states = {
        item.provider_id: item.circuit_state
        for item in db.scalars(select(ProviderHealth).order_by(ProviderHealth.provider_id)).all()
    }
    settings = get_settings()
    return OperationsStatusResponse(
        database="connected",
        pending_notification_jobs=pending_count,
        oldest_pending_notification_at=pending.created_at if pending else None,
        provider_circuit_states=states,
        live_polling_enabled=(
            settings.enable_live_sarasota_dispatch_polling
            or settings.enable_live_miami_dade_dispatch_polling
            or settings.enable_live_broward_dispatch_polling
        ),
        learned_model_serving_enabled=settings.enable_learned_model_serving,
    )
