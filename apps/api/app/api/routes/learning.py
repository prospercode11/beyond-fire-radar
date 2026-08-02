from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.dependencies import AdminUser, CurrentUser, DbSession, OpportunityReviewer, request_id
from app.learning.service import (
    create_dataset_snapshot,
    create_drift_report,
    learning_policy,
    promote_model,
    replay_model,
    rollback_model,
    train_model,
)
from app.models import ModelDriftReport, ModelRelease, ModelReplayRun, TrainingDatasetSnapshot
from app.schemas import (
    LearningControlRequest,
    LearningDatasetCreateRequest,
    LearningDatasetResponse,
    LearningDriftRequest,
    LearningDriftResponse,
    LearningModelResponse,
    LearningPolicyResponse,
    LearningReplayRequest,
    LearningReplayResponse,
    LearningTrainRequest,
)

router = APIRouter(prefix="/api/v1/learning", tags=["learning"])


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _dataset_response(item: TrainingDatasetSnapshot) -> LearningDatasetResponse:
    return LearningDatasetResponse(
        id=item.id,
        dataset_version=item.dataset_version,
        feature_set_id=item.feature_set_id,
        label_set_id=item.label_set_id,
        source_manifest_id=item.source_manifest_id,
        as_of=_aware(item.as_of),
        status=item.status,
        mechanics_only=item.mechanics_only,
        real_data_eligible=item.real_data_eligible,
        row_count=item.row_count,
        incident_count=item.incident_count,
        filters=item.filters,
        source_provenance=item.source_provenance,
        split_assignments=item.split_assignments,
        split_report=item.split_report,
        leakage_report=item.leakage_report,
        blocked_reasons=item.blocked_reasons,
        created_by=item.created_by,
        created_at=_aware(item.created_at),
    )


def _model_response(item: ModelRelease) -> LearningModelResponse:
    return LearningModelResponse(
        id=item.id,
        model_version=item.model_version,
        algorithm=item.algorithm,
        status=item.status,
        feature_set_id=item.feature_set_id,
        label_set_id=item.label_set_id,
        dataset_snapshot_id=item.dataset_snapshot_id,
        predecessor_id=item.predecessor_id,
        artifact=item.artifact,
        evaluation=item.evaluation,
        training_report=item.training_report,
        model_card=item.model_card,
        approval_required=item.approval_required,
        approved_by=item.approved_by,
        approved_at=_aware(item.approved_at) if item.approved_at else None,
        deployed_at=_aware(item.deployed_at) if item.deployed_at else None,
        rolled_back_at=_aware(item.rolled_back_at) if item.rolled_back_at else None,
        inactive_reason=item.inactive_reason,
        created_by=item.created_by,
        created_at=_aware(item.created_at),
    )


def _replay_response(item: ModelReplayRun) -> LearningReplayResponse:
    return LearningReplayResponse(
        id=item.id,
        model_release_id=item.model_release_id,
        dataset_snapshot_id=item.dataset_snapshot_id,
        metrics=item.metrics,
        accuracy_claim_allowed=item.accuracy_claim_allowed,
        created_by=item.created_by,
        created_at=_aware(item.created_at),
    )


def _drift_response(item: ModelDriftReport) -> LearningDriftResponse:
    return LearningDriftResponse(
        id=item.id,
        model_release_id=item.model_release_id,
        baseline_snapshot_id=item.baseline_snapshot_id,
        comparison_snapshot_id=item.comparison_snapshot_id,
        feature_version=item.feature_version,
        status=item.status,
        threshold=item.threshold,
        metrics=item.metrics,
        created_by=item.created_by,
        created_at=_aware(item.created_at),
    )


def _error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    return HTTPException(status_code=404 if detail.endswith("not found") else 422, detail=detail)


@router.post(
    "/datasets", response_model=LearningDatasetResponse, status_code=status.HTTP_201_CREATED
)
def create_dataset(
    request: LearningDatasetCreateRequest,
    user: OpportunityReviewer,
    db: DbSession,
    rid: str = Depends(request_id),
) -> LearningDatasetResponse:
    try:
        snapshot = create_dataset_snapshot(
            db,
            manifest_id=request.manifest_id,
            target_label_type=request.target_label_type,
            mechanics_only=request.mechanics_only,
            idempotency_key=request.idempotency_key,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise _error(exc) from exc
    db.commit()
    return _dataset_response(snapshot)


@router.get("/datasets", response_model=list[LearningDatasetResponse])
def list_datasets(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[LearningDatasetResponse]:
    rows = db.scalars(
        select(TrainingDatasetSnapshot)
        .order_by(TrainingDatasetSnapshot.created_at.desc(), TrainingDatasetSnapshot.id)
        .limit(limit)
    ).all()
    return [_dataset_response(item) for item in rows]


@router.get("/datasets/{snapshot_id}", response_model=LearningDatasetResponse)
def get_dataset(snapshot_id: str, user: CurrentUser, db: DbSession) -> LearningDatasetResponse:
    snapshot = db.get(TrainingDatasetSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="training dataset snapshot not found")
    return _dataset_response(snapshot)


@router.post(
    "/models/train", response_model=LearningModelResponse, status_code=status.HTTP_201_CREATED
)
def train_learning_model(
    request: LearningTrainRequest,
    user: OpportunityReviewer,
    db: DbSession,
    rid: str = Depends(request_id),
) -> LearningModelResponse:
    try:
        release = train_model(
            db,
            snapshot_id=request.dataset_snapshot_id,
            algorithm=request.algorithm,
            mechanics_only=request.mechanics_only,
            idempotency_key=request.idempotency_key,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise _error(exc) from exc
    db.commit()
    return _model_response(release)


@router.get("/models", response_model=list[LearningModelResponse])
def list_learning_models(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[LearningModelResponse]:
    rows = db.scalars(
        select(ModelRelease).order_by(ModelRelease.created_at.desc(), ModelRelease.id).limit(limit)
    ).all()
    return [_model_response(item) for item in rows]


@router.get("/models/{model_release_id}", response_model=LearningModelResponse)
def get_learning_model(
    model_release_id: str, user: CurrentUser, db: DbSession
) -> LearningModelResponse:
    release = db.get(ModelRelease, model_release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="model release not found")
    return _model_response(release)


@router.post("/models/{model_release_id}/replay", response_model=LearningReplayResponse)
def replay_learning_model(
    model_release_id: str,
    request: LearningReplayRequest,
    user: OpportunityReviewer,
    db: DbSession,
    rid: str = Depends(request_id),
) -> LearningReplayResponse:
    try:
        replay = replay_model(
            db,
            model_release_id=model_release_id,
            dataset_snapshot_id=request.dataset_snapshot_id,
            idempotency_key=request.idempotency_key,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise _error(exc) from exc
    db.commit()
    return _replay_response(replay)


@router.post("/models/{model_release_id}/promote", response_model=LearningModelResponse)
def promote_learning_model(
    model_release_id: str,
    request: LearningControlRequest,
    user: AdminUser,
    db: DbSession,
    rid: str = Depends(request_id),
) -> LearningModelResponse:
    try:
        release = promote_model(
            db,
            model_release_id=model_release_id,
            idempotency_key=request.idempotency_key,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise _error(exc) from exc
    db.commit()
    return _model_response(release)


@router.post("/models/{model_release_id}/rollback", response_model=LearningModelResponse)
def rollback_learning_model(
    model_release_id: str,
    request: LearningControlRequest,
    user: AdminUser,
    db: DbSession,
    rid: str = Depends(request_id),
) -> LearningModelResponse:
    try:
        release = rollback_model(
            db,
            model_release_id=model_release_id,
            idempotency_key=request.idempotency_key,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise _error(exc) from exc
    db.commit()
    return _model_response(release)


@router.post("/drift", response_model=LearningDriftResponse, status_code=status.HTTP_201_CREATED)
def create_learning_drift_report(
    request: LearningDriftRequest,
    user: OpportunityReviewer,
    db: DbSession,
    rid: str = Depends(request_id),
) -> LearningDriftResponse:
    try:
        report = create_drift_report(
            db,
            baseline_snapshot_id=request.baseline_snapshot_id,
            comparison_snapshot_id=request.comparison_snapshot_id,
            model_release_id=request.model_release_id,
            idempotency_key=request.idempotency_key,
            actor_user_id=user.id,
            request_id=rid,
        )
    except ValueError as exc:
        raise _error(exc) from exc
    db.commit()
    return _drift_response(report)


@router.get("/policy", response_model=LearningPolicyResponse)
def get_learning_policy(user: CurrentUser, db: DbSession) -> LearningPolicyResponse:
    return LearningPolicyResponse(**learning_policy(db))
