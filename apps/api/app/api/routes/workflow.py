from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from sqlalchemy import select

from app.audit import record_audit
from app.dependencies import CurrentUser, DbSession, IncidentEditor, request_id
from app.models import (
    CanonicalIncident,
    ClientImport,
    ExistingClientRecord,
    IncidentAssignment,
    InternalAlert,
    NotificationJob,
    User,
    WorkflowNote,
)
from app.schemas import (
    AlertGenerationResponse,
    AssignmentRequest,
    AssignmentResponse,
    ClientImportResponse,
    ExistingClientRecordResponse,
    NotificationJobResponse,
    WorkflowAlertActionRequest,
    WorkflowAlertResponse,
    WorkflowNoteCreateRequest,
    WorkflowNoteResponse,
)
from app.workflow.service import (
    add_note,
    assign_incident,
    change_alert,
    generate_alerts,
    normalize_client_address,
)

router = APIRouter(prefix="/api/v1/workflow", tags=["internal-workflow"])


def _alert_response(item: InternalAlert) -> WorkflowAlertResponse:
    return WorkflowAlertResponse(
        id=item.id,
        incident_id=item.incident_id,
        score_run_id=item.score_run_id,
        dedupe_key=item.dedupe_key,
        alert_type=item.alert_type,
        severity=item.severity,
        status=item.status,
        title=item.title,
        summary=item.summary,
        evidence_snapshot=item.evidence_snapshot,
        suppression_reason=item.suppression_reason,
        acknowledged_by=item.acknowledged_by,
        acknowledged_at=item.acknowledged_at,
        resolved_by=item.resolved_by,
        resolved_at=item.resolved_at,
        snoozed_until=item.snoozed_until,
        revoked_by=item.revoked_by,
        revoked_at=item.revoked_at,
        escalated_by=item.escalated_by,
        escalated_at=item.escalated_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/alerts", response_model=list[WorkflowAlertResponse])
def list_alerts(
    user: CurrentUser,
    db: DbSession,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[WorkflowAlertResponse]:
    query = select(InternalAlert).order_by(InternalAlert.created_at.desc()).limit(limit)
    if status_filter:
        query = query.where(InternalAlert.status == status_filter)
    return [_alert_response(item) for item in db.scalars(query).all()]


@router.post("/alerts/generate", response_model=AlertGenerationResponse)
def generate_alerts_route(
    user: IncidentEditor,
    db: DbSession,
    incident_id: Optional[str] = None,
    rid: str = Depends(request_id),
) -> AlertGenerationResponse:
    if incident_id is not None and db.get(CanonicalIncident, incident_id) is None:
        raise HTTPException(status_code=404, detail="incident not found")
    result = generate_alerts(db, actor_user_id=user.id, request_id=rid, incident_id=incident_id)
    db.commit()
    return AlertGenerationResponse(**result)


def _apply_alert_action(
    action: str,
    alert_id: str,
    request: WorkflowAlertActionRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str,
) -> WorkflowAlertResponse:
    alert = db.get(InternalAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    try:
        change_alert(
            db,
            alert,
            action=action,
            reason=request.reason,
            actor_user_id=user.id,
            request_id=rid,
            snoozed_until=request.snoozed_until,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _alert_response(alert)


@router.post("/alerts/{alert_id}/acknowledge", response_model=WorkflowAlertResponse)
def acknowledge_alert(
    alert_id: str,
    request: WorkflowAlertActionRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> WorkflowAlertResponse:
    return _apply_alert_action("acknowledge", alert_id, request, user, db, rid)


@router.post("/alerts/{alert_id}/snooze", response_model=WorkflowAlertResponse)
def snooze_alert(
    alert_id: str,
    request: WorkflowAlertActionRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> WorkflowAlertResponse:
    return _apply_alert_action("snooze", alert_id, request, user, db, rid)


@router.post("/alerts/{alert_id}/resolve", response_model=WorkflowAlertResponse)
def resolve_alert(
    alert_id: str,
    request: WorkflowAlertActionRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> WorkflowAlertResponse:
    return _apply_alert_action("resolve", alert_id, request, user, db, rid)


@router.post("/alerts/{alert_id}/suppress", response_model=WorkflowAlertResponse)
def suppress_alert(
    alert_id: str,
    request: WorkflowAlertActionRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> WorkflowAlertResponse:
    return _apply_alert_action("suppress", alert_id, request, user, db, rid)


@router.post("/alerts/{alert_id}/revoke", response_model=WorkflowAlertResponse)
def revoke_alert(
    alert_id: str,
    request: WorkflowAlertActionRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> WorkflowAlertResponse:
    return _apply_alert_action("revoke", alert_id, request, user, db, rid)


@router.post("/alerts/{alert_id}/escalate", response_model=WorkflowAlertResponse)
def escalate_alert(
    alert_id: str,
    request: WorkflowAlertActionRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> WorkflowAlertResponse:
    return _apply_alert_action("escalate", alert_id, request, user, db, rid)


@router.post("/alerts/{alert_id}/unsuppress", response_model=WorkflowAlertResponse)
def unsuppress_alert(
    alert_id: str,
    request: WorkflowAlertActionRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> WorkflowAlertResponse:
    return _apply_alert_action("unsuppress", alert_id, request, user, db, rid)


@router.get("/notifications", response_model=list[NotificationJobResponse])
def list_notifications(
    user: CurrentUser, db: DbSession, limit: int = Query(default=100, ge=1, le=500)
) -> list[NotificationJobResponse]:
    jobs = db.scalars(
        select(NotificationJob).order_by(NotificationJob.created_at.desc()).limit(limit)
    ).all()
    return [_notification_response(item) for item in jobs]


def _notification_response(item: NotificationJob) -> NotificationJobResponse:
    return NotificationJobResponse(
        id=item.id,
        alert_id=item.alert_id,
        channel=item.channel,
        status=item.status,
        attempt_count=item.attempt_count,
        last_attempt_at=item.last_attempt_at,
        error_message=item.error_message,
        created_at=item.created_at,
    )


@router.post("/notifications/dispatch", response_model=list[NotificationJobResponse])
def dispatch_notifications(
    user: IncidentEditor, db: DbSession, rid: str = Depends(request_id)
) -> list[NotificationJobResponse]:
    jobs = db.scalars(
        select(NotificationJob)
        .where(NotificationJob.status == "pending")
        .order_by(NotificationJob.created_at, NotificationJob.id)
        .limit(500)
    ).all()
    result: list[NotificationJobResponse] = []
    for job in jobs:
        alert = db.get(InternalAlert, job.alert_id)
        job.attempt_count += 1
        job.last_attempt_at = datetime.now(timezone.utc)
        if job.channel != "in_app":
            job.status = "rejected"
            job.error_message = "notification channel is not enabled"
        elif alert is None or alert.status in {"suppressed", "revoked", "resolved"}:
            job.status = "suppressed"
            job.error_message = "alert is suppressed, revoked, or resolved"
        else:
            # In-app is the only enabled channel. No email, SMS, phone, or consumer delivery exists.
            job.status = "delivered"
            job.error_message = None
        record_audit(
            db,
            action="workflow.notification.dispatched",
            resource_type="notification_job",
            resource_id=job.id,
            actor_user_id=user.id,
            request_id=rid,
            metadata={"channel": job.channel, "status": job.status},
        )
        result.append(_notification_response(job))
    db.commit()
    return result


def _assignment_response(
    item: Optional[IncidentAssignment], incident_id: str
) -> AssignmentResponse:
    if item is None:
        return AssignmentResponse(
            id=None,
            incident_id=incident_id,
            assignee_user_id=None,
            role=None,
            reason=None,
            actor_user_id=None,
            ended_at=None,
            created_at=None,
        )
    return AssignmentResponse(
        id=item.id,
        incident_id=item.incident_id,
        assignee_user_id=item.assignee_user_id,
        role=item.role,
        reason=item.reason,
        actor_user_id=item.actor_user_id,
        ended_at=item.ended_at,
        created_at=item.created_at,
    )


@router.get("/incidents/{incident_id}/assignment", response_model=AssignmentResponse)
def get_assignment(incident_id: str, user: CurrentUser, db: DbSession) -> AssignmentResponse:
    if db.get(CanonicalIncident, incident_id) is None:
        raise HTTPException(status_code=404, detail="incident not found")
    item = db.scalar(
        select(IncidentAssignment).where(
            IncidentAssignment.incident_id == incident_id, IncidentAssignment.ended_at.is_(None)
        )
    )
    return _assignment_response(item, incident_id)


@router.post("/incidents/{incident_id}/assignment", response_model=AssignmentResponse)
def set_assignment(
    incident_id: str,
    request: AssignmentRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> AssignmentResponse:
    if db.get(CanonicalIncident, incident_id) is None:
        raise HTTPException(status_code=404, detail="incident not found")
    if request.assignee_user_id is not None:
        assignee = db.get(User, request.assignee_user_id)
        if assignee is None or not assignee.is_active:
            raise HTTPException(status_code=422, detail="assignee user is not active")
    item = assign_incident(
        db,
        incident_id,
        request.assignee_user_id,
        role=request.role,
        reason=request.reason,
        actor_user_id=user.id,
        request_id=rid,
    )
    db.commit()
    return _assignment_response(item, incident_id)


@router.get("/incidents/{incident_id}/notes", response_model=list[WorkflowNoteResponse])
def list_notes(incident_id: str, user: CurrentUser, db: DbSession) -> list[WorkflowNoteResponse]:
    if db.get(CanonicalIncident, incident_id) is None:
        raise HTTPException(status_code=404, detail="incident not found")
    notes = db.scalars(
        select(WorkflowNote)
        .where(WorkflowNote.incident_id == incident_id)
        .order_by(WorkflowNote.created_at, WorkflowNote.id)
    ).all()
    return [
        WorkflowNoteResponse(
            id=item.id,
            incident_id=item.incident_id,
            body=item.body,
            note_type=item.note_type,
            author_user_id=item.author_user_id,
            created_at=item.created_at,
        )
        for item in notes
    ]


@router.post(
    "/incidents/{incident_id}/notes",
    response_model=WorkflowNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_note(
    incident_id: str,
    request: WorkflowNoteCreateRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> WorkflowNoteResponse:
    if db.get(CanonicalIncident, incident_id) is None:
        raise HTTPException(status_code=404, detail="incident not found")
    note = add_note(
        db, incident_id, request.body, request.note_type, actor_user_id=user.id, request_id=rid
    )
    db.commit()
    return WorkflowNoteResponse(
        id=note.id,
        incident_id=note.incident_id,
        body=note.body,
        note_type=note.note_type,
        author_user_id=note.author_user_id,
        created_at=note.created_at,
    )


@router.post(
    "/clients/import", response_model=ClientImportResponse, status_code=status.HTTP_201_CREATED
)
async def import_clients(
    user: IncidentEditor,
    db: DbSession,
    file: Annotated[UploadFile, File(...)],
    idempotency_key: Annotated[
        str, Header(..., alias="Idempotency-Key", min_length=8, max_length=320)
    ],
    rid: str = Depends(request_id),
) -> ClientImportResponse:
    payload = await file.read()
    if len(payload) > 5_000_000:
        raise HTTPException(status_code=413, detail="client import exceeds configured size limit")
    content_hash = hashlib.sha256(payload).hexdigest()
    existing = db.scalar(
        select(ClientImport).where(ClientImport.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if existing.content_hash != content_hash:
            raise HTTPException(
                status_code=409, detail="idempotency key was used with different content"
            )
        record_audit(
            db,
            action="workflow.client_import.replayed",
            resource_type="client_import",
            resource_id=existing.id,
            actor_user_id=user.id,
            request_id=rid,
            metadata={"idempotency_key": idempotency_key, "content_hash": content_hash},
        )
        db.commit()
        return ClientImportResponse(
            id=existing.id,
            source_filename=existing.source_filename,
            status=existing.status,
            accepted_row_count=existing.accepted_row_count,
            rejected_row_count=existing.rejected_row_count,
            content_hash=existing.content_hash,
            created_at=existing.created_at,
        )
    try:
        rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="client import must be UTF-8 CSV") from exc
    client_import = ClientImport(
        id=str(uuid4()),
        source_filename=file.filename or "clients.csv",
        idempotency_key=idempotency_key,
        content_hash=content_hash,
        status="imported",
        raw_payload_reference=f"sha256:{content_hash}",
        created_by=user.id,
    )
    accepted = rejected = 0
    db.add(client_import)
    db.flush()
    for row_number, row in enumerate(rows, start=2):
        client_key = (row.get("client_key") or row.get("client_id") or "").strip()
        address = normalize_client_address(row.get("address") or row.get("normalized_address"))
        parcel_id = (row.get("parcel_id") or "").strip() or None
        if not client_key or (not address and not parcel_id):
            rejected += 1
            continue
        do_not_contact = (row.get("do_not_contact") or "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }
        db.add(
            ExistingClientRecord(
                id=str(uuid4()),
                client_import_id=client_import.id,
                row_number=row_number,
                client_key=client_key,
                normalized_address=address,
                parcel_id=parcel_id,
                do_not_contact=do_not_contact,
                source_note=(row.get("source_note") or "").strip() or None,
                raw_payload=json.dumps(row, sort_keys=True),
            )
        )
        accepted += 1
    client_import.accepted_row_count = accepted
    client_import.rejected_row_count = rejected
    client_import.status = "imported_with_rejections" if rejected else "imported"
    record_audit(
        db,
        action="workflow.client_import.created",
        resource_type="client_import",
        resource_id=client_import.id,
        actor_user_id=user.id,
        request_id=rid,
        metadata={
            "accepted_row_count": accepted,
            "rejected_row_count": rejected,
            "source_filename": client_import.source_filename,
        },
    )
    db.commit()
    return ClientImportResponse(
        id=client_import.id,
        source_filename=client_import.source_filename,
        status=client_import.status,
        accepted_row_count=accepted,
        rejected_row_count=rejected,
        content_hash=content_hash,
        created_at=client_import.created_at,
    )


@router.get("/clients", response_model=list[ExistingClientRecordResponse])
def list_clients(
    user: CurrentUser, db: DbSession, limit: int = Query(default=500, ge=1, le=2000)
) -> list[ExistingClientRecordResponse]:
    records = db.scalars(
        select(ExistingClientRecord)
        .order_by(ExistingClientRecord.created_at.desc(), ExistingClientRecord.id)
        .limit(limit)
    ).all()
    return [
        ExistingClientRecordResponse(
            id=item.id,
            client_import_id=item.client_import_id,
            row_number=item.row_number,
            client_key=item.client_key,
            normalized_address=item.normalized_address,
            parcel_id=item.parcel_id,
            do_not_contact=item.do_not_contact,
            source_note=item.source_note,
            created_at=item.created_at,
        )
        for item in records
    ]
