from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select

from app.audit import record_audit
from app.config import get_settings
from app.dependencies import AdminUser, CurrentUser, DbSession, IngestionUser, request_id
from app.models import (
    DispatchObservation,
    ImportErrorRecord,
    ImportJob,
    ParserVersion,
    Provider,
    ProviderHealth,
    ProviderRetrieval,
    RawSnapshot,
    SchemaAlert,
)
from app.providers.ingestion import (
    DispatchIngestionService,
    IdempotencyConflict,
    SnapshotTooLarge,
    report_from_job,
    seed_parser_versions,
)
from app.providers.parsing import PARSER_VERSION
from app.providers.registry import build_registry
from app.schemas import (
    ImportErrorResponse,
    ImportJobResponse,
    ObservationResponse,
    ParserComparisonResponse,
    ParserVersionResponse,
    ProviderHealthResponse,
    ProviderListResponse,
    ProviderResponse,
    SchemaAlertResponse,
)

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


def _provider_response(provider: Provider) -> ProviderResponse:
    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        source_authority=provider.source_authority,
        geographic_coverage=provider.geographic_coverage,
        data_type=provider.data_type,
        authorized_use_status=provider.authorized_use_status,
        enabled=provider.enabled,
        schema_version=provider.schema_version,
        parser_version=provider.parser_version,
        limitations=provider.limitations,
    )


@router.get("", response_model=ProviderListResponse)
def list_providers(user: CurrentUser, db: DbSession) -> ProviderListResponse:
    providers = db.scalars(select(Provider).order_by(Provider.id)).all()
    return ProviderListResponse(providers=[_provider_response(provider) for provider in providers])


def _report_response(report) -> ImportJobResponse:
    return ImportJobResponse(**report.__dict__)


@router.get("/{provider_id}/health", response_model=ProviderHealthResponse)
def provider_health(provider_id: str, user: CurrentUser, db: DbSession) -> ProviderHealthResponse:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    health = db.scalar(select(ProviderHealth).where(ProviderHealth.provider_id == provider_id))
    if health is None:
        raise HTTPException(status_code=404, detail="provider health has not been initialized")
    return ProviderHealthResponse(
        provider_id=provider_id,
        last_successful_retrieval=health.last_successful_retrieval,
        last_changed_retrieval=health.last_changed_retrieval,
        last_snapshot_hash=health.last_snapshot_hash,
        last_retrieval_status=health.last_retrieval_status,
        failure_count=health.failure_count,
        circuit_state=health.circuit_state,
        schema_drift_detected=health.schema_drift_detected,
        schema_alert_count=health.schema_alert_count,
        known_status_note=health.known_status_note,
    )


@router.get("/{provider_id}/parser-versions", response_model=list[ParserVersionResponse])
def parser_versions(
    provider_id: str, user: CurrentUser, db: DbSession
) -> list[ParserVersionResponse]:
    if db.get(Provider, provider_id) is None:
        raise HTTPException(status_code=404, detail="provider not found")
    versions = db.scalars(
        select(ParserVersion)
        .where(ParserVersion.provider_id == provider_id)
        .order_by(ParserVersion.version)
    ).all()
    return [
        ParserVersionResponse(
            provider_id=item.provider_id,
            version=item.version,
            format=item.format,
            expected_fields=item.expected_fields,
            required_fields=item.required_fields,
            active=item.active,
        )
        for item in versions
    ]


@router.get("/{provider_id}/retrievals", response_model=list[ImportJobResponse])
def retrievals(provider_id: str, user: CurrentUser, db: DbSession) -> list[ImportJobResponse]:
    if db.get(Provider, provider_id) is None:
        raise HTTPException(status_code=404, detail="provider not found")
    jobs = db.scalars(
        select(ImportJob)
        .where(ImportJob.provider_id == provider_id)
        .order_by(ImportJob.created_at.desc())
        .limit(100)
    ).all()
    return [_report_response(report_from_job(db, job, replayed=False)) for job in jobs]


@router.get("/{provider_id}/parser-compare", response_model=ParserComparisonResponse)
def parser_compare(
    provider_id: str,
    retrieval_id: str,
    user: CurrentUser,
    db: DbSession,
    parser_version: str = PARSER_VERSION,
) -> ParserComparisonResponse:
    provider = db.get(Provider, provider_id)
    retrieval = db.get(ProviderRetrieval, retrieval_id)
    if provider is None or retrieval is None or retrieval.provider_id != provider_id:
        raise HTTPException(status_code=404, detail="provider retrieval not found")
    try:
        result = DispatchIngestionService(get_settings()).compare(db, retrieval, parser_version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ParserComparisonResponse(
        retrieval_id=retrieval_id,
        parser_version=result.parser_version,
        schema_version=result.schema_version,
        format=result.format,
        normalized_record_count=len(result.rows),
        rejected_record_count=sum(1 for issue in result.issues if issue.row_number is not None),
        schema_alerts=[
            issue.message
            for issue in result.issues
            if issue.code in {"schema_drift", "schema_warning", "zero_row_anomaly"}
        ],
    )


@router.post(
    "/{provider_id}/snapshots",
    response_model=ImportJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_snapshot(
    provider_id: str,
    user: IngestionUser,
    db: DbSession,
    file: Annotated[UploadFile, File(...)],
    idempotency_key: Annotated[
        str, Header(..., alias="Idempotency-Key", min_length=8, max_length=200)
    ],
    authorized_snapshot: Annotated[bool, Form()] = False,
    rid: str = Depends(request_id),
) -> ImportJobResponse:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    chunks = []
    total = 0
    maximum = get_settings().max_snapshot_bytes
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > maximum:
            raise HTTPException(status_code=413, detail="snapshot exceeds configured size limit")
        chunks.append(chunk)
    payload = b"".join(chunks)
    try:
        report = DispatchIngestionService(get_settings()).ingest(
            db,
            provider=provider,
            user_id=user.id,
            filename=file.filename or "snapshot.upload",
            content_type=file.content_type,
            payload=payload,
            idempotency_key=idempotency_key,
            authorized_snapshot=authorized_snapshot,
            request_id=rid,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SnapshotTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _report_response(report)


@router.post("/{provider_id}/disable", response_model=ProviderResponse)
def disable_provider(
    provider_id: str, user: AdminUser, db: DbSession, rid: str = Depends(request_id)
) -> ProviderResponse:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    provider.enabled = False
    record_audit(
        db,
        action="provider.disabled",
        resource_type="provider",
        resource_id=provider.id,
        actor_user_id=user.id,
        request_id=rid,
    )
    db.commit()
    return _provider_response(provider)


def seed_providers(db: DbSession) -> None:
    registry = build_registry(get_settings())
    for metadata in registry.list_metadata():
        existing = db.get(Provider, metadata.provider_id)
        if existing is None:
            db.add(
                Provider(
                    id=metadata.provider_id,
                    name=metadata.name,
                    source_authority=metadata.source_authority,
                    geographic_coverage=metadata.geographic_coverage,
                    data_type=metadata.data_type,
                    authentication_method=metadata.authentication_method,
                    authorized_use_status=metadata.authorized_use_status,
                    enabled=metadata.enabled_by_default,
                    polling_interval_seconds=metadata.polling_interval_seconds,
                    schema_version=metadata.schema_version,
                    parser_version=metadata.parser_version,
                    license_note=metadata.license_note,
                    limitations=metadata.limitations,
                    contact_note=metadata.contact_note,
                )
            )
            db.add(
                ProviderHealth(
                    id=metadata.provider_id,
                    provider_id=metadata.provider_id,
                    known_status_note="No dispatch snapshot retrieval has run yet.",
                )
            )
        else:
            existing.schema_version = metadata.schema_version
            existing.parser_version = metadata.parser_version
            existing.name = metadata.name
            existing.source_authority = metadata.source_authority
            existing.geographic_coverage = metadata.geographic_coverage
            existing.data_type = metadata.data_type
            existing.authentication_method = metadata.authentication_method
            existing.authorized_use_status = metadata.authorized_use_status
            existing.enabled = metadata.enabled_by_default
            existing.polling_interval_seconds = metadata.polling_interval_seconds
            existing.license_note = metadata.license_note
            existing.limitations = metadata.limitations
            existing.contact_note = metadata.contact_note
            if (
                db.scalar(
                    select(ProviderHealth).where(ProviderHealth.provider_id == metadata.provider_id)
                )
                is None
            ):
                db.add(
                    ProviderHealth(
                        id=metadata.provider_id,
                        provider_id=metadata.provider_id,
                        known_status_note="No property or dispatch retrieval has run yet.",
                    )
                )
    seed_parser_versions(db)


retrieval_router = APIRouter(prefix="/api/v1/retrievals", tags=["dispatch-ingestion"])


@retrieval_router.get("/{retrieval_id}/observations", response_model=list[ObservationResponse])
def observations(retrieval_id: str, user: CurrentUser, db: DbSession) -> list[ObservationResponse]:
    if db.get(ProviderRetrieval, retrieval_id) is None:
        raise HTTPException(status_code=404, detail="retrieval not found")
    # The retrieval-to-snapshot join is kept explicit so observations cannot leak across snapshots.
    raw_snapshot = db.scalar(select(RawSnapshot).where(RawSnapshot.retrieval_id == retrieval_id))
    if raw_snapshot is None:
        return []
    items = db.scalars(
        select(DispatchObservation)
        .where(DispatchObservation.raw_snapshot_id == raw_snapshot.id)
        .order_by(DispatchObservation.id)
    ).all()
    return [_observation_response(item) for item in items]


@retrieval_router.get("/{retrieval_id}/raw")
def raw_snapshot(retrieval_id: str, user: CurrentUser, db: DbSession) -> Response:
    raw_snapshot = db.scalar(select(RawSnapshot).where(RawSnapshot.retrieval_id == retrieval_id))
    if raw_snapshot is None:
        raise HTTPException(status_code=404, detail="raw snapshot not found")
    try:
        payload = DispatchIngestionService(get_settings()).store.read(
            raw_snapshot.payload_reference
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="raw snapshot payload is unavailable") from exc
    return Response(
        content=payload,
        media_type=raw_snapshot.content_type,
        headers={"X-Content-SHA256": raw_snapshot.content_hash},
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


@retrieval_router.get("/{retrieval_id}/schema-alerts", response_model=list[SchemaAlertResponse])
def schema_alerts(retrieval_id: str, user: CurrentUser, db: DbSession) -> list[SchemaAlertResponse]:
    items = db.scalars(
        select(SchemaAlert)
        .where(SchemaAlert.retrieval_id == retrieval_id)
        .order_by(SchemaAlert.created_at)
    ).all()
    return [
        SchemaAlertResponse(
            id=item.id,
            retrieval_id=item.retrieval_id,
            provider_id=item.provider_id,
            parser_version=item.parser_version,
            severity=item.severity,
            code=item.code,
            observed_fields=item.observed_fields,
            missing_required_fields=item.missing_required_fields,
            unexpected_fields=item.unexpected_fields,
            message=item.message,
            created_at=item.created_at,
        )
        for item in items
    ]


@retrieval_router.get("/{retrieval_id}/errors", response_model=list[ImportErrorResponse])
def import_errors(retrieval_id: str, user: CurrentUser, db: DbSession) -> list[ImportErrorResponse]:
    retrieval = db.scalar(select(ProviderRetrieval).where(ProviderRetrieval.id == retrieval_id))
    if retrieval is None:
        raise HTTPException(status_code=404, detail="retrieval not found")
    jobs = db.scalars(select(ImportJob).where(ImportJob.retrieval_id == retrieval_id)).all()
    if not jobs:
        return []
    items = db.scalars(
        select(ImportErrorRecord)
        .where(ImportErrorRecord.import_job_id.in_([job.id for job in jobs]))
        .order_by(ImportErrorRecord.created_at)
    ).all()
    return [
        ImportErrorResponse(
            id=item.id,
            import_job_id=item.import_job_id,
            row_number=item.row_number,
            code=item.code,
            message=item.message,
        )
        for item in items
    ]
