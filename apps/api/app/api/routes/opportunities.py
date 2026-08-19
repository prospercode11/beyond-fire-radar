from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.dependencies import (
    AdminUser,
    CurrentUser,
    DbSession,
    IncidentEditor,
    OpportunityReviewer,
    request_id,
)
from app.models import (
    CanonicalIncident,
    OpportunityScoreFeature,
    OpportunityScoreRun,
    ScoringVersion,
)
from app.opportunities.scoring import (
    _current_override,
    create_scoring_version,
    ensure_fire_score_runs,
    incident_score_eligibility,
    record_override,
    rollback_score,
    score_incident,
)
from app.schemas import (
    OpportunityScoreFeatureResponse,
    OpportunityScoreOverrideRequest,
    OpportunityScoreRequest,
    OpportunityScoreResponse,
    ScoringVersionCreateRequest,
    ScoringVersionResponse,
)

router = APIRouter(tags=["opportunity-scoring"])


def _response(db: DbSession, run: OpportunityScoreRun) -> OpportunityScoreResponse:
    features = db.scalars(
        select(OpportunityScoreFeature)
        .where(OpportunityScoreFeature.score_run_id == run.id)
        .order_by(OpportunityScoreFeature.feature_name)
    ).all()
    override = _current_override(db, run.incident_id)
    tier = run.evidence_tier
    alert_eligibility = run.alert_eligibility
    hard_gate = run.hard_gate_status
    if override is not None:
        if override.decision == "suppress":
            tier = "suppressed"
        elif override.decision == "promote_review":
            tier = "priority_review"
        elif override.decision == "hold":
            tier = "held"
        alert_eligibility = False
        hard_gate = "human_override"
    return OpportunityScoreResponse(
        id=run.id,
        incident_id=run.incident_id,
        property_match_run_id=run.property_match_run_id,
        property_provider_id=run.property_provider_id,
        scoring_version=run.scoring_version,
        previous_score_run_id=run.previous_score_run_id,
        as_of=run.as_of,
        status=run.status,
        provisional_score=run.provisional_score,
        evidence_tier=tier,
        alert_eligibility=alert_eligibility,
        abstention_reason=run.abstention_reason,
        hard_gate_status=hard_gate,
        explanation=run.explanation,
        source_observation_ids=run.source_observation_ids,
        available_at=run.available_at,
        created_at=run.created_at,
        completed_at=run.completed_at,
        is_current=run.is_current,
        features=[
            OpportunityScoreFeatureResponse(
                id=item.id,
                feature_name=item.feature_name,
                value=item.value,
                status=item.status,
                contribution=item.contribution,
                evidence=item.evidence,
                source_observation_ids=item.source_observation_ids,
                available_at=item.available_at,
                feature_version=item.feature_version,
                explanation=item.explanation,
            )
            for item in features
        ],
        human_override=(
            {
                "id": override.id,
                "decision": override.decision,
                "reason": override.reason,
                "actor_user_id": override.actor_user_id,
                "created_at": override.created_at,
            }
            if override
            else None
        ),
    )


def _current_score(db: DbSession, incident_id: str) -> Optional[OpportunityScoreRun]:
    run = db.scalar(
        select(OpportunityScoreRun).where(
            OpportunityScoreRun.incident_id == incident_id,
            OpportunityScoreRun.is_current.is_(True),
        )
    )
    if run is None:
        return None
    incident = db.get(CanonicalIncident, incident_id)
    if incident is None:
        return None
    # Current detail visibility follows the incident's current classification.
    # The score run retains its historical as-of boundary for audit, but a later
    # crash/alarm reclassification must remove the old score from the live view.
    eligible, _, _ = incident_score_eligibility(db, incident)
    return run if eligible else None


@router.get("/api/v1/opportunities/scoring-versions", response_model=list[ScoringVersionResponse])
def list_scoring_versions(user: CurrentUser, db: DbSession) -> list[ScoringVersionResponse]:
    return [
        ScoringVersionResponse(
            id=item.id,
            version=item.version,
            status=item.status,
            component_versions=item.component_versions,
            priors=item.priors,
            rules=item.rules,
            description=item.description,
            created_at=item.created_at,
        )
        for item in db.scalars(select(ScoringVersion).order_by(ScoringVersion.created_at)).all()
    ]


@router.post(
    "/api/v1/opportunities/scoring-versions",
    response_model=ScoringVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_scoring_release(
    request: ScoringVersionCreateRequest,
    user: AdminUser,
    db: DbSession,
    rid: str = Depends(request_id),
) -> ScoringVersionResponse:
    try:
        version = create_scoring_version(
            db,
            version_name=request.version,
            component_versions=request.component_versions,
            priors=request.priors,
            rules=request.rules,
            description=request.description,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return ScoringVersionResponse(
        id=version.id,
        version=version.version,
        status=version.status,
        component_versions=version.component_versions,
        priors=version.priors,
        rules=version.rules,
        description=version.description,
        created_at=version.created_at,
    )


@router.get("/api/v1/opportunities", response_model=list[OpportunityScoreResponse])
def list_opportunities(
    user: CurrentUser,
    db: DbSession,
    evidence_tier: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OpportunityScoreResponse]:
    query = (
        select(OpportunityScoreRun)
        .where(OpportunityScoreRun.is_current.is_(True))
        .order_by(
            OpportunityScoreRun.provisional_score.desc(),
            OpportunityScoreRun.created_at.desc(),
            OpportunityScoreRun.id.desc(),
        )
    )
    if evidence_tier:
        query = query.where(OpportunityScoreRun.evidence_tier == evidence_tier)
    if status_filter:
        query = query.where(OpportunityScoreRun.status == status_filter)
    scoreable = []
    for item in db.scalars(query).all():
        incident = db.get(CanonicalIncident, item.incident_id)
        if incident is None:
            continue
        # Do not expose a historical fire score after newer evidence makes the
        # current incident non-fire. Historical runs remain inspectable by ID.
        eligible, _, _ = incident_score_eligibility(db, incident)
        if eligible:
            scoreable.append(item)
    return [_response(db, item) for item in scoreable[offset : offset + limit]]


@router.post("/api/v1/opportunities/rescore-fire")
def rescore_fire_opportunities(user: OpportunityReviewer, db: DbSession) -> dict[str, int]:
    """Refresh every active fire and recompute only changed or incomplete runs.

    The scorer still inspects every active incident, repairs stale taxonomy projections,
    and rematches incidents whose property snapshot or observations changed. Unchanged
    incidents are deliberately skipped so a refresh does not rewrite the large county
    property projection and score history unnecessarily.
    """

    rescored = ensure_fire_score_runs(db, actor_user_id=user.id, force=False)
    db.commit()
    return {"rescored": rescored}


@router.post(
    "/api/v1/incidents/{incident_id}/opportunity-score",
    response_model=OpportunityScoreResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_opportunity_score(
    incident_id: str,
    request: OpportunityScoreRequest,
    user: IncidentEditor,
    db: DbSession,
) -> OpportunityScoreResponse:
    incident = db.get(CanonicalIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    try:
        run = score_incident(
            db,
            incident,
            property_provider_id=request.property_provider_id,
            actor_user_id=user.id,
            scoring_version=request.scoring_version,
            as_of=request.as_of,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _response(db, run)


@router.post(
    "/api/v1/incidents/{incident_id}/opportunity-score/rescore",
    response_model=OpportunityScoreResponse,
    status_code=status.HTTP_201_CREATED,
)
def rescore_opportunity(
    incident_id: str,
    request: OpportunityScoreRequest,
    user: IncidentEditor,
    db: DbSession,
) -> OpportunityScoreResponse:
    return create_opportunity_score(incident_id, request, user, db)


@router.get(
    "/api/v1/incidents/{incident_id}/opportunity-score",
    response_model=OpportunityScoreResponse,
)
def get_opportunity_score(
    incident_id: str, user: CurrentUser, db: DbSession
) -> OpportunityScoreResponse:
    run = _current_score(db, incident_id)
    if run is None:
        raise HTTPException(status_code=404, detail="opportunity score not found")
    return _response(db, run)


@router.post(
    "/api/v1/opportunities/{score_id}/rollback",
    response_model=OpportunityScoreResponse,
)
def rollback_opportunity_score(
    score_id: str,
    user: OpportunityReviewer,
    db: DbSession,
    rid: str = Depends(request_id),
) -> OpportunityScoreResponse:
    run = db.get(OpportunityScoreRun, score_id)
    if run is None:
        raise HTTPException(status_code=404, detail="opportunity score not found")
    try:
        restored = rollback_score(db, run, actor_user_id=user.id, request_id=rid)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _response(db, restored)


@router.post(
    "/api/v1/incidents/{incident_id}/opportunity-score/decisions",
    response_model=OpportunityScoreResponse,
)
def decide_opportunity_score(
    incident_id: str,
    request: OpportunityScoreOverrideRequest,
    user: OpportunityReviewer,
    db: DbSession,
    rid: str = Depends(request_id),
) -> OpportunityScoreResponse:
    incident = db.get(CanonicalIncident, incident_id)
    run = _current_score(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    if run is None:
        raise HTTPException(status_code=404, detail="opportunity score not found")
    try:
        record_override(
            db,
            incident,
            score_run=run,
            decision=request.decision,
            reason=request.reason,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _response(db, run)
