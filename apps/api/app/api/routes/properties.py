from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.audit import record_audit
from app.config import get_settings
from app.dependencies import CurrentUser, DbSession, PropertyImporter, PropertyReviewer, request_id
from app.models import (
    CanonicalIncident,
    IncidentPropertyCandidate,
    IncidentPropertyMatchRun,
    Parcel,
    ParcelAddressAlias,
    PropertyBuilding,
    PropertyFieldValue,
    PropertyImport,
    PropertyImportError,
    PropertyMappingProfile,
    PropertySourceRow,
    Provider,
)
from app.properties.resolution import (
    current_property_decision,
    record_property_decision,
    run_property_match,
)
from app.properties.service import (
    PropertyImportConflict,
    PropertyImportReport,
    PropertyImportService,
)
from app.schemas import (
    ParcelResponse,
    PropertyCandidateResponse,
    PropertyImportErrorResponse,
    PropertyImportPreviewResponse,
    PropertyImportResponse,
    PropertyMappingProfileCreate,
    PropertyMappingProfileResponse,
    PropertyMatchDecisionRequest,
    PropertyMatchDecisionResponse,
    PropertyMatchRunRequest,
    PropertyMatchRunResponse,
)

import_router = APIRouter(prefix="/api/v1/properties", tags=["properties"])
match_router = APIRouter(prefix="/api/v1/incidents", tags=["property-resolution"])


def _mapping_from_json(mapping_json: Optional[str]) -> Optional[dict[str, str]]:
    if not mapping_json:
        return None
    try:
        mapping = json.loads(mapping_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="mapping_json must be valid JSON") from exc
    if not isinstance(mapping, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in mapping.items()
    ):
        raise HTTPException(
            status_code=422, detail="mapping_json must be an object of string fields"
        )
    return mapping


def _profile_mapping(
    db: DbSession, provider_id: str, profile_id: Optional[str]
) -> Optional[dict[str, str]]:
    if not profile_id:
        return None
    profile = db.get(PropertyMappingProfile, profile_id)
    if profile is None or profile.provider_id != provider_id:
        raise HTTPException(status_code=404, detail="mapping profile not found for provider")
    return profile.mapping


def _preview_response(parsed) -> PropertyImportPreviewResponse:
    return PropertyImportPreviewResponse(
        format=parsed.format,
        headers=parsed.headers,
        mapping=parsed.mapping,
        row_count=len(parsed.rows),
        rejected_row_count=parsed.rejected_row_count,
        warnings=[issue.message for issue in parsed.issues if issue.severity == "warning"],
        errors=[issue.message for issue in parsed.issues if issue.severity != "warning"],
        sample_rows=[row.fields for row in parsed.rows[:5]],
    )


def _import_response(report) -> PropertyImportResponse:
    return PropertyImportResponse(**report.__dict__)


def _import_record_response(item: PropertyImport) -> PropertyImportResponse:
    return _import_response(
        PropertyImportReport(
            property_import_id=item.id,
            provider_id=item.provider_id,
            status=item.status,
            format={".csv": "csv", ".xlsx": "xlsx", ".zip": "zip"}.get(
                Path(item.source_filename).suffix.lower(), "unknown"
            ),
            source_version=item.source_version,
            content_hash=item.content_hash,
            normalized_row_count=item.normalized_row_count,
            rejected_row_count=item.rejected_row_count,
            removed_row_count=item.removed_row_count,
            replayed=False,
            mapping={},
            warnings=[],
            errors=[item.error_message] if item.error_message else [],
            acquisition_mode=item.acquisition_mode,
            authorization_basis=item.authorization_basis,
            source_filename=item.source_filename,
            parser_version=item.parser_version,
            schema_version=item.schema_version,
            effective_at=item.effective_at,
            retrieved_at=item.retrieved_at,
            raw_payload_reference=item.raw_payload_reference,
        )
    )


@import_router.post(
    "/mapping-profiles", response_model=PropertyMappingProfileResponse, status_code=201
)
def create_mapping_profile(
    request: PropertyMappingProfileCreate,
    user: PropertyImporter,
    db: DbSession,
    rid: str = Depends(request_id),
) -> PropertyMappingProfileResponse:
    existing = db.scalar(
        select(PropertyMappingProfile).where(
            PropertyMappingProfile.provider_id == request.provider_id,
            PropertyMappingProfile.name == request.name,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="mapping profile already exists")
    profile = PropertyMappingProfile(
        id=str(__import__("uuid").uuid4()),
        provider_id=request.provider_id,
        name=request.name,
        mapping=request.mapping,
        version="property-mapping.v1",
        created_by=user.id,
    )
    db.add(profile)
    record_audit(
        db,
        action="property.mapping_profile_created",
        resource_type="property_mapping_profile",
        resource_id=profile.id,
        actor_user_id=user.id,
        request_id=rid,
        metadata={"provider_id": request.provider_id, "name": request.name},
    )
    db.commit()
    return PropertyMappingProfileResponse(
        id=profile.id,
        provider_id=profile.provider_id,
        name=profile.name,
        mapping=profile.mapping,
        version=profile.version,
        created_at=profile.created_at,
    )


@import_router.get("/mapping-profiles", response_model=list[PropertyMappingProfileResponse])
def list_mapping_profiles(
    user: CurrentUser,
    db: DbSession,
    provider_id: Optional[str] = None,
) -> list[PropertyMappingProfileResponse]:
    query = select(PropertyMappingProfile).order_by(PropertyMappingProfile.name)
    if provider_id:
        query = query.where(PropertyMappingProfile.provider_id == provider_id)
    return [
        PropertyMappingProfileResponse(
            id=item.id,
            provider_id=item.provider_id,
            name=item.name,
            mapping=item.mapping,
            version=item.version,
            created_at=item.created_at,
        )
        for item in db.scalars(query).all()
    ]


@import_router.post("/imports/preview", response_model=PropertyImportPreviewResponse)
async def preview_property_import(
    user: PropertyImporter,
    db: DbSession,
    file: Annotated[UploadFile, File(...)],
    provider_id: Annotated[str, Form(...)],
    mapping_json: Annotated[Optional[str], Form()] = None,
    mapping_profile_id: Annotated[Optional[str], Form()] = None,
) -> PropertyImportPreviewResponse:
    payload = await file.read()
    mapping = _mapping_from_json(mapping_json) or _profile_mapping(
        db, provider_id, mapping_profile_id
    )
    parsed = PropertyImportService(get_settings()).preview(
        payload,
        content_type=file.content_type,
        filename=file.filename or "property.import",
        mapping=mapping,
    )
    return _preview_response(parsed)


@import_router.post(
    "/imports", response_model=PropertyImportResponse, status_code=status.HTTP_201_CREATED
)
async def import_property_file(
    user: PropertyImporter,
    db: DbSession,
    file: Annotated[UploadFile, File(...)],
    provider_id: Annotated[str, Form(...)],
    source_version: Annotated[str, Form(min_length=1, max_length=120)],
    idempotency_key: Annotated[str, Form(min_length=8, max_length=200)],
    import_mode: Annotated[str, Form()] = "full",
    effective_at: Annotated[Optional[datetime], Form()] = None,
    mapping_json: Annotated[Optional[str], Form()] = None,
    mapping_profile_id: Annotated[Optional[str], Form()] = None,
    authorized_snapshot: Annotated[bool, Form()] = False,
    rid: str = Depends(request_id),
) -> PropertyImportResponse:
    payload = await file.read()
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="property provider not found")
    if provider.data_type != "property_bulk_file":
        raise HTTPException(status_code=422, detail="provider is not a property bulk-file provider")
    mapping = _mapping_from_json(mapping_json)
    try:
        report = PropertyImportService(get_settings()).import_file(
            db,
            provider_id=provider_id,
            user_id=user.id,
            filename=file.filename or "property.import",
            content_type=file.content_type,
            payload=payload,
            source_version=source_version,
            import_mode=import_mode,
            effective_at=effective_at,
            mapping=mapping,
            mapping_profile_id=mapping_profile_id,
            idempotency_key=idempotency_key,
            authorized_snapshot=authorized_snapshot,
            request_id=rid,
        )
    except PropertyImportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _import_response(report)


@import_router.get("/imports", response_model=list[PropertyImportResponse])
def list_property_imports(
    user: CurrentUser,
    db: DbSession,
    provider_id: Optional[str] = None,
) -> list[PropertyImportResponse]:
    query = select(PropertyImport).order_by(PropertyImport.created_at.desc()).limit(100)
    if provider_id:
        query = query.where(PropertyImport.provider_id == provider_id)
    return [_import_record_response(item) for item in db.scalars(query).all()]


@import_router.get("/imports/{import_id}/errors", response_model=list[PropertyImportErrorResponse])
def property_import_errors(
    import_id: str, user: CurrentUser, db: DbSession
) -> list[PropertyImportErrorResponse]:
    if db.get(PropertyImport, import_id) is None:
        raise HTTPException(status_code=404, detail="property import not found")
    return [
        PropertyImportErrorResponse(
            id=item.id,
            property_import_id=item.property_import_id,
            row_number=item.row_number,
            code=item.code,
            message=item.message,
            raw_payload=item.raw_payload,
        )
        for item in db.scalars(
            select(PropertyImportError)
            .where(PropertyImportError.property_import_id == import_id)
            .order_by(PropertyImportError.created_at, PropertyImportError.id)
        ).all()
    ]


@import_router.post("/imports/{import_id}/rollback", response_model=PropertyImportResponse)
def rollback_property_import(
    import_id: str,
    user: PropertyReviewer,
    db: DbSession,
    rid: str = Depends(request_id),
) -> PropertyImportResponse:
    import_record = db.get(PropertyImport, import_id)
    if import_record is None:
        raise HTTPException(status_code=404, detail="property import not found")
    try:
        report = PropertyImportService(get_settings()).rollback(
            db, import_record, actor_user_id=user.id, request_id=rid
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _import_response(report)


def _parcel_response(db: DbSession, parcel: Parcel) -> ParcelResponse:
    import_record = (
        db.get(PropertyImport, parcel.current_import_id) if parcel.current_import_id else None
    )
    source_row = (
        db.get(PropertySourceRow, parcel.current_source_row_id)
        if parcel.current_source_row_id
        else None
    )
    field_values = (
        db.scalars(
            select(PropertyFieldValue)
            .where(
                PropertyFieldValue.parcel_id == parcel.id,
                PropertyFieldValue.property_import_id == parcel.current_import_id,
            )
            .order_by(PropertyFieldValue.field_name)
        ).all()
        if parcel.current_import_id
        else []
    )
    aliases = db.scalars(
        select(ParcelAddressAlias)
        .where(ParcelAddressAlias.parcel_id == parcel.id)
        .order_by(ParcelAddressAlias.alias_type, ParcelAddressAlias.id)
    ).all()
    buildings = db.scalars(
        select(PropertyBuilding)
        .where(PropertyBuilding.parcel_id == parcel.id)
        .order_by(PropertyBuilding.building_key)
    ).all()
    return ParcelResponse(
        id=parcel.id,
        provider_id=parcel.provider_id,
        parcel_id=parcel.parcel_id,
        is_active=parcel.is_active,
        source_version=parcel.source_version,
        effective_at=parcel.effective_at,
        situs_original=parcel.situs_original,
        normalized_address=parcel.normalized_address,
        address_precision=parcel.address_precision,
        municipality=parcel.municipality,
        postal_code=parcel.postal_code,
        property_use_code=parcel.property_use_code,
        property_use_category=parcel.property_use_category,
        owner_name=parcel.owner_name,
        mailing_address=parcel.mailing_address,
        year_built=parcel.year_built,
        building_area=parcel.building_area,
        number_of_buildings=parcel.number_of_buildings,
        number_of_units=parcel.number_of_units,
        stories=parcel.stories,
        latitude=parcel.latitude,
        longitude=parcel.longitude,
        master_parcel_id=parcel.master_parcel_id,
        data_quality=parcel.data_quality,
        current_import_id=parcel.current_import_id,
        current_source_row_id=parcel.current_source_row_id,
        provenance={
            "import": (
                {
                    "id": import_record.id,
                    "provider_id": import_record.provider_id,
                    "source_filename": import_record.source_filename,
                    "source_version": import_record.source_version,
                    "parser_version": import_record.parser_version,
                    "schema_version": import_record.schema_version,
                    "acquisition_mode": import_record.acquisition_mode,
                    "authorization_basis": import_record.authorization_basis,
                    "effective_at": import_record.effective_at,
                    "retrieved_at": import_record.retrieved_at,
                    "raw_payload_reference": import_record.raw_payload_reference,
                }
                if import_record
                else None
            ),
            "source_row": (
                {
                    "id": source_row.id,
                    "row_number": source_row.row_number,
                    "source_filename": source_row.source_filename,
                    "source_parcel_id": source_row.source_parcel_id,
                    "row_hash": source_row.row_hash,
                    "raw_payload": source_row.raw_payload,
                    "normalized_fields": source_row.normalized_fields,
                    "status": source_row.status,
                }
                if source_row
                else None
            ),
            "fields": [
                {
                    "field_name": item.field_name,
                    "raw_value": item.raw_value,
                    "normalized_value": item.normalized_value,
                    "transformation": item.transformation,
                    "transformation_version": item.transformation_version,
                    "confidence": item.confidence,
                    "available_at": item.available_at,
                    "retrieved_at": item.retrieved_at,
                    "source_row_id": item.source_row_id,
                }
                for item in field_values
            ],
            "aliases": [
                {
                    "id": item.id,
                    "property_import_id": item.property_import_id,
                    "alias_type": item.alias_type,
                    "original_value": item.original_value,
                    "normalized_address": item.normalized_address,
                }
                for item in aliases
            ],
            "buildings": [
                {
                    "id": item.id,
                    "property_import_id": item.property_import_id,
                    "building_key": item.building_key,
                    "unit_count": item.unit_count,
                    "stories": item.stories,
                    "building_area": item.building_area,
                }
                for item in buildings
            ],
        },
    )


@import_router.get("/parcels/{parcel_id}", response_model=ParcelResponse)
def get_parcel(
    parcel_id: str,
    user: CurrentUser,
    db: DbSession,
    provider_id: Optional[str] = None,
) -> ParcelResponse:
    parcel = db.get(Parcel, parcel_id)
    if parcel is None:
        query = select(Parcel).where(Parcel.parcel_id == parcel_id)
        if provider_id:
            query = query.where(Parcel.provider_id == provider_id)
        matches = db.scalars(query.limit(2)).all()
        if len(matches) > 1:
            raise HTTPException(
                status_code=409,
                detail="parcel ID is ambiguous; provide provider_id",
            )
        parcel = matches[0] if matches else None
    if parcel is None:
        raise HTTPException(status_code=404, detail="parcel not found")
    return _parcel_response(db, parcel)


def _candidate_response(
    db: DbSession, candidate: IncidentPropertyCandidate
) -> PropertyCandidateResponse:
    parcel = db.get(Parcel, candidate.parcel_id)
    if parcel is None:
        raise HTTPException(status_code=500, detail="candidate parcel is missing")
    return PropertyCandidateResponse(
        id=candidate.id,
        incident_id=candidate.incident_id,
        parcel_id=candidate.parcel_id,
        rank=candidate.rank,
        match_score=candidate.match_score,
        score_margin=candidate.score_margin,
        classification=candidate.classification,
        recommendation_status=candidate.recommendation_status,
        is_abstained=candidate.is_abstained,
        supporting_evidence=candidate.supporting_evidence,
        contradictory_evidence=candidate.contradictory_evidence,
        features=candidate.features,
        explanation=candidate.explanation,
        property_data_quality=candidate.property_data_quality,
        parcel=_parcel_response(db, parcel).model_dump(),
    )


def _run_response(db: DbSession, run: IncidentPropertyMatchRun) -> PropertyMatchRunResponse:
    candidates = db.scalars(
        select(IncidentPropertyCandidate)
        .where(IncidentPropertyCandidate.match_run_id == run.id)
        .order_by(IncidentPropertyCandidate.rank)
    ).all()
    decision = current_property_decision(db, run.incident_id)
    return PropertyMatchRunResponse(
        id=run.id,
        incident_id=run.incident_id,
        property_provider_id=run.property_provider_id,
        property_import_id=run.property_import_id,
        status=run.status,
        matcher_version=run.matcher_version,
        address_normalization_version=run.address_normalization_version,
        candidate_count=run.candidate_count,
        abstention_reason=run.abstention_reason,
        source_observation_ids=run.source_observation_ids,
        created_at=run.created_at,
        completed_at=run.completed_at,
        candidates=[_candidate_response(db, candidate) for candidate in candidates],
        current_human_decision=(
            {
                "id": decision.id,
                "decision": decision.decision,
                "candidate_id": decision.candidate_id,
                "parcel_id": decision.parcel_id,
                "corrected_address": decision.corrected_address,
                "reason": decision.reason,
                "created_at": decision.created_at,
            }
            if decision
            else None
        ),
    )


@match_router.post(
    "/{incident_id}/property-matches", response_model=PropertyMatchRunResponse, status_code=201
)
def create_property_match(
    incident_id: str,
    request: PropertyMatchRunRequest,
    user: PropertyImporter,
    db: DbSession,
) -> PropertyMatchRunResponse:
    incident = db.get(CanonicalIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    try:
        run = run_property_match(
            db,
            incident,
            property_provider_id=request.property_provider_id,
            property_import_id=request.property_import_id,
            actor_user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _run_response(db, run)


@match_router.get("/{incident_id}/property-matches", response_model=PropertyMatchRunResponse)
def get_property_match(
    incident_id: str, user: CurrentUser, db: DbSession
) -> PropertyMatchRunResponse:
    run = db.scalar(
        select(IncidentPropertyMatchRun)
        .where(IncidentPropertyMatchRun.incident_id == incident_id)
        .order_by(IncidentPropertyMatchRun.created_at.desc())
    )
    if run is None:
        raise HTTPException(status_code=404, detail="property match run not found")
    return _run_response(db, run)


@match_router.post(
    "/{incident_id}/property-matches/reprocess",
    response_model=PropertyMatchRunResponse,
    status_code=201,
)
def reprocess_property_match(
    incident_id: str,
    request: PropertyMatchRunRequest,
    user: PropertyImporter,
    db: DbSession,
) -> PropertyMatchRunResponse:
    return create_property_match(incident_id, request, user, db)


@match_router.post(
    "/{incident_id}/property-matches/decisions",
    response_model=PropertyMatchDecisionResponse,
    status_code=201,
)
def decide_property_match(
    incident_id: str,
    request: PropertyMatchDecisionRequest,
    user: PropertyReviewer,
    db: DbSession,
    rid: str = Depends(request_id),
) -> PropertyMatchDecisionResponse:
    incident = db.get(CanonicalIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    candidate = None
    if request.candidate_id:
        candidate = db.get(IncidentPropertyCandidate, request.candidate_id)
        if candidate is None or candidate.incident_id != incident_id:
            raise HTTPException(status_code=404, detail="property candidate not found")
    try:
        decision = record_property_decision(
            db,
            incident,
            decision=request.decision,
            reason=request.reason,
            actor_user_id=user.id,
            request_id=rid,
            candidate=candidate,
            corrected_address=request.corrected_address,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return PropertyMatchDecisionResponse(
        id=decision.id,
        incident_id=decision.incident_id,
        candidate_id=decision.candidate_id,
        parcel_id=decision.parcel_id,
        decision=decision.decision,
        corrected_address=decision.corrected_address,
        reason=decision.reason,
        actor_user_id=decision.actor_user_id,
        created_at=decision.created_at,
    )
