from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.config import get_settings
from app.dependencies import CurrentUser, DbSession, IncidentEditor, IngestionUser, request_id
from app.incidents.service import (
    merge_incidents,
    process_retrieval,
    rescore_incident,
    split_incident,
    transition_state,
)
from app.models import (
    CanonicalIncident,
    DispatchObservation,
    IncidentAlias,
    IncidentEvidence,
    IncidentMatchDecision,
    IncidentObservationLink,
    IncidentTimelineEvent,
    ProviderRetrieval,
    RawSnapshot,
)
from app.schemas import (
    IncidentDetailResponse,
    IncidentMergeRequest,
    IncidentProcessResponse,
    IncidentSplitRequest,
    IncidentStateUpdate,
    IncidentSummaryResponse,
    ObservationResponse,
)

router = APIRouter(prefix="/api/v1/incidents", tags=["incident-intelligence"])


def _process_response(run) -> IncidentProcessResponse:
    return IncidentProcessResponse(
        processing_run_id=run.id,
        retrieval_id=run.retrieval_id,
        provider_id=run.provider_id,
        acquisition_mode=run.acquisition_mode,
        status=run.status,
        linkage_version=run.linkage_version,
        classification_version=run.classification_version,
        observation_count=run.observation_count,
        linked_count=run.linked_count,
        new_incident_count=run.new_incident_count,
        review_count=run.review_count,
        contradiction_count=run.contradiction_count,
    )


def _summary(db, incident: CanonicalIncident) -> IncidentSummaryResponse:
    count = (
        db.scalar(
            select(func.count())
            .select_from(IncidentObservationLink)
            .where(
                IncidentObservationLink.incident_id == incident.id,
                IncidentObservationLink.is_current.is_(True),
            )
        )
        or 0
    )
    return IncidentSummaryResponse(
        id=incident.id,
        provider_id=incident.provider_id,
        state=incident.state,
        classification_family=incident.classification_family,
        classification_version=incident.classification_version,
        classification_confidence=incident.classification_confidence,
        confidence_band=incident.confidence_band,
        review_band=incident.review_band,
        first_event_time=incident.first_event_time,
        last_event_time=incident.last_event_time,
        canonical_location=incident.canonical_location,
        contradiction_count=incident.contradiction_count,
        review_signal_status=incident.review_signal_status,
        review_signal_issued_at=incident.review_signal_issued_at,
        review_signal_revoked_at=incident.review_signal_revoked_at,
        review_signal_revocation_reason=incident.review_signal_revocation_reason,
        observation_count=count,
        is_active=incident.is_active,
        merged_into_id=incident.merged_into_id,
    )


def _observation_response(item: DispatchObservation) -> ObservationResponse:
    return ObservationResponse(
        id=item.id,
        raw_dispatch_row_id=item.raw_dispatch_row_id,
        source_record_id=item.source_record_id,
        source_event_id=item.source_event_id,
        source_case_number=item.source_case_number,
        agency=item.agency,
        station=item.station,
        event_time=item.event_time,
        retrieved_at=item.retrieved_at,
        original_event_type=item.original_event_type,
        normalized_event_family=item.normalized_event_family,
        original_location=item.original_location,
        location_precision=item.location_precision,
        latitude=item.latitude,
        longitude=item.longitude,
        grid=item.grid,
        parser_confidence=item.parser_confidence,
        parser_version=item.parser_version,
        taxonomy_version=item.taxonomy_version,
        raw_payload_reference=item.raw_payload_reference,
    )


def _detail(db, incident: CanonicalIncident) -> IncidentDetailResponse:
    links = db.scalars(
        select(IncidentObservationLink)
        .where(
            IncidentObservationLink.incident_id == incident.id,
            IncidentObservationLink.is_current.is_(True),
        )
        .order_by(IncidentObservationLink.created_at, IncidentObservationLink.id)
    ).all()
    all_links = db.scalars(
        select(IncidentObservationLink)
        .where(IncidentObservationLink.incident_id == incident.id)
        .order_by(IncidentObservationLink.created_at, IncidentObservationLink.id)
    ).all()
    observation_ids = [link.observation_id for link in links]
    observations = (
        db.scalars(
            select(DispatchObservation).where(DispatchObservation.id.in_(observation_ids))
        ).all()
        if observation_ids
        else []
    )
    by_id = {item.id: item for item in observations}
    timelines = db.scalars(
        select(IncidentTimelineEvent)
        .where(IncidentTimelineEvent.incident_id == incident.id)
        .order_by(IncidentTimelineEvent.occurred_at, IncidentTimelineEvent.id)
    ).all()
    evidence = db.scalars(
        select(IncidentEvidence)
        .where(IncidentEvidence.incident_id == incident.id)
        .order_by(IncidentEvidence.created_at, IncidentEvidence.id)
    ).all()
    decisions = db.scalars(
        select(IncidentMatchDecision)
        .where(
            (IncidentMatchDecision.candidate_incident_id == incident.id)
            | IncidentMatchDecision.observation_id.in_(observation_ids)
        )
        .order_by(IncidentMatchDecision.created_at, IncidentMatchDecision.id)
    ).all()
    aliases = db.scalars(
        select(IncidentAlias)
        .where(IncidentAlias.incident_id == incident.id)
        .order_by(IncidentAlias.created_at, IncidentAlias.id)
    ).all()
    source_snapshot_ids = sorted({item.raw_snapshot_id for item in observations})
    source_retrievals = (
        db.scalars(
            select(ProviderRetrieval)
            .join(RawSnapshot, RawSnapshot.retrieval_id == ProviderRetrieval.id)
            .where(RawSnapshot.id.in_(source_snapshot_ids))
        ).all()
        if source_snapshot_ids
        else []
    )
    summary = _summary(db, incident)
    return IncidentDetailResponse(
        **summary.model_dump(),
        canonical_event_type=incident.canonical_event_type,
        canonical_grid=incident.canonical_grid,
        canonical_agency=incident.canonical_agency,
        canonical_station=incident.canonical_station,
        classification_explanation=incident.classification_explanation,
        current_explanation=incident.current_explanation,
        source_acquisition_modes=sorted({item.acquisition_mode for item in source_retrievals}),
        source_retrieval_ids=sorted({item.id for item in source_retrievals}),
        observations=[
            _observation_response(by_id[item_id]) for item_id in observation_ids if item_id in by_id
        ],
        source_row_ids=[link.raw_dispatch_row_id for link in links],
        relationship_history=[
            {
                "id": link.id,
                "observation_id": link.observation_id,
                "raw_dispatch_row_id": link.raw_dispatch_row_id,
                "link_type": link.link_type,
                "is_current": link.is_current,
                "decision_id": link.decision_id,
                "created_by": link.created_by,
                "created_at": link.created_at,
            }
            for link in all_links
        ],
        timeline=[
            {
                "id": item.id,
                "event_type": item.event_type,
                "occurred_at": item.occurred_at,
                "prior_state": item.prior_state,
                "new_state": item.new_state,
                "source_observation_id": item.source_observation_id,
                "details": item.details,
                "actor_user_id": item.actor_user_id,
            }
            for item in timelines
        ],
        evidence=[
            {
                "id": item.id,
                "observation_id": item.observation_id,
                "evidence_type": item.evidence_type,
                "code": item.code,
                "summary": item.summary,
                "details": item.details,
                "created_at": item.created_at,
            }
            for item in evidence
        ],
        match_decisions=[
            {
                "id": item.id,
                "observation_id": item.observation_id,
                "reference_observation_id": item.reference_observation_id,
                "decision": item.decision,
                "stage": item.stage,
                "score": item.score,
                "confidence_band": item.confidence_band,
                "model_version": item.model_version,
                "features": item.features,
                "explanation": item.explanation,
                "created_at": item.created_at,
            }
            for item in decisions
        ],
        aliases=[
            {
                "id": item.id,
                "observation_id": item.observation_id,
                "alias_type": item.alias_type,
                "alias_value": item.alias_value,
                "collision": item.collision,
                "created_at": item.created_at,
            }
            for item in aliases
        ],
    )


@router.post(
    "/process/retrievals/{retrieval_id}",
    response_model=IncidentProcessResponse,
    status_code=status.HTTP_201_CREATED,
)
def process_dispatch_retrieval(
    retrieval_id: str,
    user: IngestionUser,
    db: DbSession,
    rid: str = Depends(request_id),
) -> IncidentProcessResponse:
    retrieval = db.get(ProviderRetrieval, retrieval_id)
    if retrieval is None:
        raise HTTPException(status_code=404, detail="retrieval not found")
    try:
        run = process_retrieval(
            db,
            retrieval,
            get_settings(),
            actor_user_id=user.id,
            reason="manual_snapshot_processing",
            request_id=rid,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _process_response(run)


@router.get("", response_model=list[IncidentSummaryResponse])
def list_incidents(
    user: CurrentUser,
    db: DbSession,
    provider_id: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    include_inactive: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[IncidentSummaryResponse]:
    query = (
        select(CanonicalIncident)
        .order_by(CanonicalIncident.first_event_time, CanonicalIncident.id)
        .limit(limit)
    )
    if provider_id:
        query = query.where(CanonicalIncident.provider_id == provider_id)
    if state:
        query = query.where(CanonicalIncident.state == state)
    if not include_inactive:
        query = query.where(CanonicalIncident.is_active.is_(True))
    return [_summary(db, item) for item in db.scalars(query).all()]


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
def get_incident(incident_id: str, user: CurrentUser, db: DbSession) -> IncidentDetailResponse:
    incident = db.get(CanonicalIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return _detail(db, incident)


@router.post("/{incident_id}/rescore", response_model=IncidentDetailResponse)
def rescore(
    incident_id: str,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> IncidentDetailResponse:
    incident = db.get(CanonicalIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    rescore_incident(db, incident, actor_user_id=user.id, request_id=rid)
    db.commit()
    return _detail(db, incident)


@router.patch("/{incident_id}/state", response_model=IncidentDetailResponse)
def update_state(
    incident_id: str,
    request: IncidentStateUpdate,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> IncidentDetailResponse:
    incident = db.get(CanonicalIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    try:
        transition_state(
            db,
            incident,
            request.state,
            reason=request.reason,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _detail(db, incident)


@router.post("/{incident_id}/merge", response_model=IncidentDetailResponse)
def merge(
    incident_id: str,
    request: IncidentMergeRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> IncidentDetailResponse:
    survivor = db.get(CanonicalIncident, incident_id)
    absorbed = db.get(CanonicalIncident, request.absorbed_incident_id)
    if survivor is None or absorbed is None:
        raise HTTPException(status_code=404, detail="incident not found")
    try:
        merge_incidents(
            db,
            survivor,
            absorbed,
            reason=request.reason,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _detail(db, survivor)


@router.post("/{incident_id}/split", response_model=IncidentDetailResponse)
def split(
    incident_id: str,
    request: IncidentSplitRequest,
    user: IncidentEditor,
    db: DbSession,
    rid: str = Depends(request_id),
) -> IncidentDetailResponse:
    incident = db.get(CanonicalIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    try:
        new_incident = split_incident(
            db,
            incident,
            request.observation_ids,
            reason=request.reason,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _detail(db, new_incident)
