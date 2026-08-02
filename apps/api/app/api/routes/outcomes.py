from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from app.audit import record_audit
from app.dependencies import CurrentUser, DbSession, OpportunityReviewer, request_id
from app.models import CanonicalIncident, IncidentOutcomeEvent, OutcomeLabel
from app.outcomes.service import (
    create_outcome_event,
    create_outcome_label,
    generate_analytics_report,
    manifest_metrics,
)
from app.schemas import (
    AnalyticsMetricResponse,
    AnalyticsReportRequest,
    AnalyticsReportResponse,
    EvaluationManifestResponse,
    IncidentOutcomeEventCreateRequest,
    IncidentOutcomeEventResponse,
    IncidentOutcomeResponse,
    OutcomeLabelCreateRequest,
    OutcomeLabelResponse,
)

router = APIRouter(tags=["outcomes-analytics"])


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _label_response(item: OutcomeLabel) -> OutcomeLabelResponse:
    return OutcomeLabelResponse(
        id=item.id,
        incident_id=item.incident_id,
        score_run_id=item.score_run_id,
        property_match_run_id=item.property_match_run_id,
        property_candidate_id=item.property_candidate_id,
        property_decision_id=item.property_decision_id,
        alert_id=item.alert_id,
        label_type=item.label_type,
        label_value=item.label_value,
        taxonomy_version=item.taxonomy_version,
        error_category=item.error_category,
        rationale=item.rationale,
        provenance=item.provenance,
        idempotency_key=item.idempotency_key,
        reviewer_user_id=item.reviewer_user_id,
        created_at=_aware(item.created_at),
    )


def _event_response(item: IncidentOutcomeEvent) -> IncidentOutcomeEventResponse:
    return IncidentOutcomeEventResponse(
        id=item.id,
        incident_id=item.incident_id,
        score_run_id=item.score_run_id,
        event_type=item.event_type,
        taxonomy_version=item.taxonomy_version,
        occurred_at=item.occurred_at,
        source=item.source,
        details=item.details,
        idempotency_key=item.idempotency_key,
        actor_user_id=item.actor_user_id,
        created_at=_aware(item.created_at),
    )


def _manifest_response(item) -> EvaluationManifestResponse:
    return EvaluationManifestResponse(
        id=item.id,
        manifest_type=item.manifest_type,
        manifest_version=item.manifest_version,
        as_of=_aware(item.as_of),
        filters=item.filters,
        incident_ids=item.incident_ids,
        score_run_ids=item.score_run_ids,
        label_ids=item.label_ids,
        outcome_event_ids=item.outcome_event_ids,
        source_acquisition_modes=item.source_acquisition_modes,
        source_retrieval_ids=item.source_retrieval_ids,
        source_property_import_ids=item.source_property_import_ids,
        source_provider_ids=item.source_provider_ids,
        source_authorization_bases=item.source_authorization_bases,
        source_snapshot_hashes=item.source_snapshot_hashes,
        source_provenance=item.source_provenance,
        claim_status=item.claim_status,
        created_by=item.created_by,
        created_at=_aware(item.created_at),
    )


def _metric_response(item) -> AnalyticsMetricResponse:
    return AnalyticsMetricResponse(
        id=item.id,
        manifest_id=item.manifest_id,
        metric_name=item.metric_name,
        metric_version=item.metric_version,
        numerator=item.numerator,
        denominator=item.denominator,
        value=item.value,
        status=item.status,
        warning=item.warning,
        details=item.details,
        created_at=_aware(item.created_at),
    )


@router.post(
    "/api/v1/incidents/{incident_id}/outcome-labels",
    response_model=OutcomeLabelResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_outcome_label(
    incident_id: str,
    request: OutcomeLabelCreateRequest,
    user: OpportunityReviewer,
    db: DbSession,
    rid: str = Depends(request_id),
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> OutcomeLabelResponse:
    key = request.idempotency_key or idempotency_header
    if not key:
        raise HTTPException(status_code=422, detail="an explicit idempotency key is required")
    try:
        label, _ = create_outcome_label(
            db,
            incident_id=incident_id,
            score_run_id=request.score_run_id,
            property_match_run_id=request.property_match_run_id,
            property_candidate_id=request.property_candidate_id,
            property_decision_id=request.property_decision_id,
            alert_id=request.alert_id,
            label_type=request.label_type,
            label_value=request.label_value,
            error_category=request.error_category,
            rationale=request.rationale,
            idempotency_key=key,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(
            status_code=404 if detail == "incident not found" else 422, detail=detail
        ) from exc
    db.commit()
    return _label_response(label)


@router.post(
    "/api/v1/incidents/{incident_id}/outcome-events",
    response_model=IncidentOutcomeEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_outcome_event(
    incident_id: str,
    request: IncidentOutcomeEventCreateRequest,
    user: OpportunityReviewer,
    db: DbSession,
    rid: str = Depends(request_id),
    idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> IncidentOutcomeEventResponse:
    key = request.idempotency_key or idempotency_header
    if not key:
        raise HTTPException(status_code=422, detail="an explicit idempotency key is required")
    try:
        event, _ = create_outcome_event(
            db,
            incident_id=incident_id,
            score_run_id=request.score_run_id,
            event_type=request.event_type,
            occurred_at=request.occurred_at,
            details=request.details,
            idempotency_key=key,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(
            status_code=404 if detail == "incident not found" else 422, detail=detail
        ) from exc
    db.commit()
    return _event_response(event)


@router.get(
    "/api/v1/incidents/{incident_id}/outcomes",
    response_model=IncidentOutcomeResponse,
)
def get_incident_outcomes(
    incident_id: str, user: CurrentUser, db: DbSession
) -> IncidentOutcomeResponse:
    if db.get(CanonicalIncident, incident_id) is None:
        raise HTTPException(status_code=404, detail="incident not found")
    labels = db.scalars(
        select(OutcomeLabel)
        .where(OutcomeLabel.incident_id == incident_id)
        .order_by(OutcomeLabel.created_at, OutcomeLabel.id)
    ).all()
    events = db.scalars(
        select(IncidentOutcomeEvent)
        .where(IncidentOutcomeEvent.incident_id == incident_id)
        .order_by(IncidentOutcomeEvent.occurred_at, IncidentOutcomeEvent.id)
    ).all()
    return IncidentOutcomeResponse(
        incident_id=incident_id,
        labels=[_label_response(item) for item in labels],
        events=[_event_response(item) for item in events],
    )


@router.post(
    "/api/v1/analytics/reports",
    response_model=AnalyticsReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_analytics_report(
    request: AnalyticsReportRequest,
    user: OpportunityReviewer,
    db: DbSession,
    rid: str = Depends(request_id),
) -> AnalyticsReportResponse:
    try:
        manifest, metrics = generate_analytics_report(
            db,
            metrics=request.metrics,
            as_of=request.as_of,
            top_k=request.top_k,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return AnalyticsReportResponse(
        manifest=_manifest_response(manifest),
        metrics=[_metric_response(item) for item in metrics],
    )


@router.get(
    "/api/v1/analytics/reports/{manifest_id}",
    response_model=AnalyticsReportResponse,
)
def get_analytics_report(
    manifest_id: str, user: CurrentUser, db: DbSession
) -> AnalyticsReportResponse:
    try:
        manifest, metrics = manifest_metrics(db, manifest_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AnalyticsReportResponse(
        manifest=_manifest_response(manifest),
        metrics=[_metric_response(item) for item in metrics],
    )


@router.post(
    "/api/v1/analytics/reports/{manifest_id}/replay",
    response_model=AnalyticsReportResponse,
)
def replay_analytics_report(
    manifest_id: str,
    user: CurrentUser,
    db: DbSession,
    rid: str = Depends(request_id),
) -> AnalyticsReportResponse:
    try:
        manifest, metrics = manifest_metrics(db, manifest_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_audit(
        db,
        action="analytics.report.replayed",
        resource_type="evaluation_manifest",
        resource_id=manifest_id,
        actor_user_id=user.id,
        request_id=rid,
        metadata={
            "manifest_version": manifest.manifest_version,
            "metric_count": len(metrics),
            "replay_mode": "frozen_manifest_rows",
        },
    )
    db.commit()
    return AnalyticsReportResponse(
        manifest=_manifest_response(manifest),
        metrics=[_metric_response(item) for item in metrics],
    )
