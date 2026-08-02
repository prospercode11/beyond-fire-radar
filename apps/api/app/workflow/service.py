from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.models import (
    CanonicalIncident,
    ExistingClientRecord,
    IncidentAssignment,
    IncidentObservationLink,
    IncidentPropertyMatchRun,
    InternalAlert,
    NotificationJob,
    OpportunityScoreOverride,
    OpportunityScoreRun,
    PropertyImport,
    ProviderRetrieval,
    RawDispatchRow,
    RawSnapshot,
    WorkflowNote,
)

TERMINAL_ALERT_STATES = {"resolved", "revoked", "suppressed"}
BLOCKED_INCIDENT_STATES = {"closed", "false_alarm", "suppressed", "downgraded"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_client_address(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()
    return normalized or None


def _source_posture(db: Session, incident_id: str) -> tuple[list[str], list[str], bool]:
    links = db.scalars(
        select(IncidentObservationLink).where(
            IncidentObservationLink.incident_id == incident_id,
            IncidentObservationLink.is_current.is_(True),
        )
    ).all()
    if not links:
        return [], [], False
    raw_rows = db.scalars(
        select(RawDispatchRow).where(
            RawDispatchRow.id.in_([link.raw_dispatch_row_id for link in links])
        )
    ).all()
    snapshot_ids = [item.raw_snapshot_id for item in raw_rows]
    rows = db.scalars(select(RawSnapshot).where(RawSnapshot.id.in_(snapshot_ids))).all()
    retrieval_ids = [item.retrieval_id for item in rows]
    retrievals = (
        db.scalars(select(ProviderRetrieval).where(ProviderRetrieval.id.in_(retrieval_ids))).all()
        if retrieval_ids
        else []
    )
    modes = sorted({item.acquisition_mode for item in retrievals})
    authorized = bool(retrievals) and all(
        item.acquisition_mode == "manual_snapshot" and bool(item.authorization_basis)
        for item in retrievals
    )
    return modes, sorted({item.id for item in retrievals}), authorized


def _current_override(db: Session, incident_id: str) -> Optional[OpportunityScoreOverride]:
    return db.scalar(
        select(OpportunityScoreOverride)
        .where(OpportunityScoreOverride.incident_id == incident_id)
        .order_by(OpportunityScoreOverride.created_at.desc(), OpportunityScoreOverride.id.desc())
    )


def _client_match(db: Session, incident: CanonicalIncident) -> Optional[ExistingClientRecord]:
    address = normalize_client_address(incident.canonical_location)
    if not address:
        return None
    return db.scalar(
        select(ExistingClientRecord)
        .where(
            ExistingClientRecord.normalized_address == address,
            ExistingClientRecord.do_not_contact.is_(True),
        )
        .order_by(ExistingClientRecord.created_at.desc(), ExistingClientRecord.id.desc())
    )


def _eligibility(
    db: Session, incident: CanonicalIncident, score: OpportunityScoreRun
) -> tuple[bool, Optional[str], list[str], list[str], bool]:
    modes, retrieval_ids, authorized = _source_posture(db, incident.id)
    override = _current_override(db, incident.id)
    client_record = _client_match(db, incident)
    if client_record is not None:
        return (
            False,
            f"suppressed: existing client record {client_record.client_key}",
            modes,
            retrieval_ids,
            authorized,
        )
    if incident.state in BLOCKED_INCIDENT_STATES:
        return (
            False,
            f"suppressed: incident state {incident.state}",
            modes,
            retrieval_ids,
            authorized,
        )
    current_score = db.scalar(
        select(OpportunityScoreRun).where(
            OpportunityScoreRun.incident_id == incident.id,
            OpportunityScoreRun.is_current.is_(True),
        )
    )
    if current_score is None or current_score.id != score.id or score.status != "scored":
        return (
            False,
            "suppressed: score run is no longer current",
            modes,
            retrieval_ids,
            authorized,
        )
    if score.property_match_run_id is None:
        return (
            False,
            "suppressed: current property evidence is missing",
            modes,
            retrieval_ids,
            authorized,
        )
    property_run = db.get(IncidentPropertyMatchRun, score.property_match_run_id)
    current_property_import = (
        db.get(PropertyImport, property_run.property_import_id)
        if property_run is not None and property_run.property_import_id
        else None
    )
    if (
        property_run is None
        or property_run.incident_id != incident.id
        or property_run.status != "matched"
        or current_property_import is None
        or not current_property_import.is_current
    ):
        return (
            False,
            "suppressed: current property evidence is unresolved or stale",
            modes,
            retrieval_ids,
            authorized,
        )
    if override is not None and override.decision == "suppress":
        return False, "suppressed: latest reviewer score decision", modes, retrieval_ids, authorized
    if not score.alert_eligibility:
        return (
            False,
            "score hard gate is not eligible for an internal alert",
            modes,
            retrieval_ids,
            authorized,
        )
    if not authorized:
        return (
            False,
            "source is not an explicitly authorized manual snapshot",
            modes,
            retrieval_ids,
            authorized,
        )
    return True, None, modes, retrieval_ids, authorized


def _snapshot(
    score: OpportunityScoreRun,
    modes: list[str],
    retrieval_ids: list[str],
    authorized: bool,
    reason: Optional[str],
) -> dict:
    return {
        "scoring_version": score.scoring_version,
        "score_run_id": score.id,
        "evidence_tier": score.evidence_tier,
        "hard_gate_status": score.hard_gate_status,
        "provisional_score": score.provisional_score,
        "source_acquisition_modes": modes,
        "source_retrieval_ids": retrieval_ids,
        "authorized_manual_snapshot": authorized,
        "eligibility_reason": reason,
        "probability_display": False,
    }


def _ensure_in_app_job(db: Session, alert_id: str) -> NotificationJob:
    job = db.scalar(
        select(NotificationJob).where(
            NotificationJob.alert_id == alert_id, NotificationJob.channel == "in_app"
        )
    )
    if job is not None:
        return job
    candidate = NotificationJob(
        id=str(uuid4()), alert_id=alert_id, channel="in_app", status="pending"
    )
    try:
        with db.begin_nested():
            db.add(candidate)
            db.flush()
    except IntegrityError:
        job = db.scalar(
            select(NotificationJob).where(
                NotificationJob.alert_id == alert_id, NotificationJob.channel == "in_app"
            )
        )
        if job is None:
            raise
        return job
    return candidate


def generate_alerts(
    db: Session,
    *,
    actor_user_id: str,
    request_id: str,
    incident_id: Optional[str] = None,
) -> dict[str, int]:
    query = select(OpportunityScoreRun).where(OpportunityScoreRun.is_current.is_(True))
    if incident_id:
        query = query.where(OpportunityScoreRun.incident_id == incident_id)
    scores = db.scalars(
        query.order_by(OpportunityScoreRun.created_at, OpportunityScoreRun.id)
    ).all()
    created = existing = suppressed = skipped = 0
    for score in scores:
        incident = db.get(CanonicalIncident, score.incident_id)
        if incident is None:
            skipped += 1
            continue
        eligible, reason, modes, retrieval_ids, authorized = _eligibility(db, incident, score)
        dedupe_key = f"incident:{incident.id}:structure-review"
        alert = db.scalar(select(InternalAlert).where(InternalAlert.dedupe_key == dedupe_key))
        if not eligible:
            skipped += 1
            if (
                alert is not None
                and reason
                and reason.startswith("suppressed")
                and alert.status not in TERMINAL_ALERT_STATES
            ):
                alert.status = "suppressed"
                alert.suppression_reason = reason
                suppressed += 1
                record_audit(
                    db,
                    action="workflow.alert.suppressed",
                    resource_type="internal_alert",
                    resource_id=alert.id,
                    actor_user_id=actor_user_id,
                    request_id=request_id,
                    metadata={"reason": reason, "dedupe_key": dedupe_key},
                )
            continue
        if alert is not None:
            existing += 1
            if alert.status not in TERMINAL_ALERT_STATES:
                alert.score_run_id = score.id
                alert.evidence_snapshot = _snapshot(score, modes, retrieval_ids, authorized, None)
            _ensure_in_app_job(db, alert.id)
            continue
        alert = InternalAlert(
            id=str(uuid4()),
            incident_id=incident.id,
            score_run_id=score.id,
            dedupe_key=dedupe_key,
            alert_type="structure_review",
            severity="review",
            status="open",
            title=f"Review {incident.canonical_location or 'unresolved location'}",
            summary="A governed internal review alert is eligible from authorized manual evidence. It is not a damage, coverage, claim, or contact conclusion.",
            evidence_snapshot=_snapshot(score, modes, retrieval_ids, authorized, None),
        )
        db.add(alert)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            alert = db.scalar(select(InternalAlert).where(InternalAlert.dedupe_key == dedupe_key))
            if alert is None:
                raise
            existing += 1
            _ensure_in_app_job(db, alert.id)
            continue
        _ensure_in_app_job(db, alert.id)
        record_audit(
            db,
            action="workflow.alert.created",
            resource_type="internal_alert",
            resource_id=alert.id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            metadata={
                "dedupe_key": dedupe_key,
                "incident_id": incident.id,
                "score_run_id": score.id,
            },
        )
        created += 1
    db.flush()
    return {
        "scanned_score_runs": len(scores),
        "created_alerts": created,
        "existing_alerts": existing,
        "suppressed_alerts": suppressed,
        "skipped_score_runs": skipped,
    }


def change_alert(
    db: Session,
    alert: InternalAlert,
    *,
    action: str,
    reason: str,
    actor_user_id: str,
    request_id: str,
    snoozed_until: Optional[datetime] = None,
) -> InternalAlert:
    if alert.status in {"resolved", "revoked"}:
        raise ValueError("terminal alerts cannot be changed")
    if alert.status == "suppressed" and action != "unsuppress":
        raise ValueError("suppressed alerts cannot be acknowledged, snoozed, or resolved")
    if action == "acknowledge":
        alert.status = "acknowledged"
        alert.acknowledged_by = actor_user_id
        alert.acknowledged_at = _now()
    elif action == "snooze":
        if snoozed_until is None or snoozed_until <= _now():
            raise ValueError("snoozed_until must be in the future")
        alert.status = "snoozed"
        alert.snoozed_until = snoozed_until
    elif action == "resolve":
        alert.status = "resolved"
        alert.resolved_by = actor_user_id
        alert.resolved_at = _now()
    elif action == "suppress":
        alert.status = "suppressed"
        alert.suppression_reason = reason
    elif action == "revoke":
        alert.status = "revoked"
        alert.revoked_by = actor_user_id
        alert.revoked_at = _now()
    elif action == "escalate":
        alert.status = "escalated"
        alert.escalated_by = actor_user_id
        alert.escalated_at = _now()
    elif action == "unsuppress":
        if alert.status != "suppressed":
            raise ValueError("alert is not suppressed")
        incident = db.get(CanonicalIncident, alert.incident_id)
        score = db.get(OpportunityScoreRun, alert.score_run_id)
        if incident is None or score is None:
            raise ValueError("alert evidence is no longer available")
        eligible, eligibility_reason, modes, retrieval_ids, authorized = _eligibility(
            db, incident, score
        )
        if not eligible:
            raise ValueError(f"alert remains ineligible: {eligibility_reason or 'unknown reason'}")
        alert.status = "open"
        alert.suppression_reason = None
        alert.evidence_snapshot = _snapshot(score, modes, retrieval_ids, authorized, None)
        job = db.scalar(
            select(NotificationJob).where(
                NotificationJob.alert_id == alert.id, NotificationJob.channel == "in_app"
            )
        )
        if job is not None and job.status == "suppressed":
            job.status = "pending"
            job.error_message = None
    else:
        raise ValueError("unsupported alert action")
    record_audit(
        db,
        action=f"workflow.alert.{action}",
        resource_type="internal_alert",
        resource_id=alert.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={"reason": reason, "status": alert.status},
    )
    return alert


def assign_incident(
    db: Session,
    incident_id: str,
    assignee_user_id: Optional[str],
    *,
    role: str,
    reason: str,
    actor_user_id: str,
    request_id: str,
) -> Optional[IncidentAssignment]:
    current = db.scalar(
        select(IncidentAssignment).where(
            IncidentAssignment.incident_id == incident_id,
            IncidentAssignment.ended_at.is_(None),
        )
    )
    now = _now()
    if current is not None:
        current.ended_at = now
    if assignee_user_id is None:
        record_audit(
            db,
            action="workflow.assignment.cleared",
            resource_type="incident",
            resource_id=incident_id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            metadata={"reason": reason},
        )
        return None
    assignment = IncidentAssignment(
        id=str(uuid4()),
        incident_id=incident_id,
        assignee_user_id=assignee_user_id,
        role=role,
        reason=reason,
        actor_user_id=actor_user_id,
    )
    db.add(assignment)
    record_audit(
        db,
        action="workflow.assignment.created",
        resource_type="incident",
        resource_id=incident_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={"assignee_user_id": assignee_user_id, "role": role, "reason": reason},
    )
    return assignment


def add_note(
    db: Session, incident_id: str, body: str, note_type: str, *, actor_user_id: str, request_id: str
) -> WorkflowNote:
    note = WorkflowNote(
        id=str(uuid4()),
        incident_id=incident_id,
        body=body,
        note_type=note_type,
        author_user_id=actor_user_id,
    )
    db.add(note)
    record_audit(
        db,
        action="workflow.note.created",
        resource_type="workflow_note",
        resource_id=note.id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        metadata={"incident_id": incident_id, "note_type": note_type},
    )
    return note
