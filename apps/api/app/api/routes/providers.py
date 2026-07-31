from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.audit import record_audit
from app.config import get_settings
from app.dependencies import AdminUser, CurrentUser, DbSession, request_id
from app.models import Provider, ProviderHealth
from app.providers.registry import build_registry
from app.schemas import ProviderListResponse, ProviderResponse

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
                    known_status_note="No retrieval has run in Phase 1.",
                )
            )
    db.commit()
