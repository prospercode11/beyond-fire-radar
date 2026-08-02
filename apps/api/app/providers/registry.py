from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from app.config import Settings
from app.providers.base import Provider, ProviderMetadata, ProviderSnapshot


class ProviderDisabledError(RuntimeError):
    pass


class SarasotaProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FixtureProvider:
    def __init__(self, metadata: ProviderMetadata, fixture_path: Path) -> None:
        self.metadata = metadata
        self.fixture_path = fixture_path

    def can_retrieve(self) -> bool:
        return True

    def retrieve(self) -> ProviderSnapshot:
        payload = self.fixture_path.read_bytes()
        return ProviderSnapshot(
            provider_id=self.metadata.provider_id,
            content_type="application/json",
            payload=payload,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            effective_at=None,
        )


class SarasotaDispatchProvider:
    def __init__(
        self,
        metadata: ProviderMetadata,
        settings: Settings,
        *,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.metadata = metadata
        self.settings = settings
        self.http_client = http_client

    def can_retrieve(self) -> bool:
        return (
            self.settings.enable_live_sarasota_dispatch_polling and self.metadata.enabled_by_default
        )

    def retrieve(self) -> ProviderSnapshot:
        if not self.can_retrieve():
            raise ProviderDisabledError(
                "live Sarasota dispatch polling is disabled by configuration"
            )

        request_headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "BeyondFireRadar/0.1 (Sarasota dispatch polling)",
        }
        try:
            if self.http_client is not None:
                response = self.http_client.get(
                    self.settings.sarasota_dispatch_url,
                    headers=request_headers,
                    timeout=self.settings.sarasota_poll_timeout_seconds,
                )
            else:
                with httpx.Client(follow_redirects=True) as client:
                    response = client.get(
                        self.settings.sarasota_dispatch_url,
                        headers=request_headers,
                        timeout=self.settings.sarasota_poll_timeout_seconds,
                    )
        except httpx.HTTPError as exc:
            raise SarasotaProviderError(
                "network_error", f"Sarasota dispatch request failed: {exc}"
            ) from exc

        if response.status_code != 200:
            raise SarasotaProviderError(
                "http_error",
                f"Sarasota dispatch returned HTTP {response.status_code}; no snapshot was imported",
            )
        payload = response.content
        if len(payload) > self.settings.max_snapshot_bytes:
            raise SarasotaProviderError(
                "snapshot_too_large",
                f"Sarasota dispatch response exceeds the configured {self.settings.max_snapshot_bytes} byte limit",
            )
        if b"911 Dispatch Reporting" not in payload or b"<table" not in payload.lower():
            raise SarasotaProviderError(
                "unexpected_response",
                "Sarasota dispatch response did not contain the expected reporting table",
            )
        content_type = response.headers.get("content-type", "text/html; charset=utf-8")
        return ProviderSnapshot(
            provider_id=self.metadata.provider_id,
            content_type=content_type,
            payload=payload,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            effective_at=None,
        )


class SarasotaPropertyAppraiserProvider:
    def __init__(self, metadata: ProviderMetadata) -> None:
        self.metadata = metadata

    def can_retrieve(self) -> bool:
        return False

    def retrieve(self) -> ProviderSnapshot:
        raise ProviderDisabledError(
            "automated Sarasota property retrieval is disabled until source terms and written authorization are confirmed"
        )


@dataclass
class ProviderRegistry:
    providers: dict[str, Provider]

    def get(self, provider_id: str) -> Provider:
        return self.providers[provider_id]

    def list_metadata(self) -> list[ProviderMetadata]:
        return [provider.metadata for provider in self.providers.values()]


def build_registry(settings: Settings) -> ProviderRegistry:
    fixture_path = (
        Path(__file__).resolve().parents[2] / "fixtures" / "sample_dispatch_snapshot.json"
    )
    property_fixture_path = (
        Path(__file__).resolve().parents[2] / "fixtures" / "sample_sarasota_property_appraiser.csv"
    )
    fixture_metadata = ProviderMetadata(
        provider_id="fixture.sarasota.dispatch",
        name="Synthetic Sarasota dispatch fixture",
        source_authority="Synthetic fixture; not an external authority",
        geographic_coverage="Sarasota County, Florida (synthetic)",
        data_type="dispatch_snapshot",
        authentication_method="none",
        authorized_use_status="test_only",
        enabled_by_default=True,
        polling_interval_seconds=None,
        schema_version="fixture.v1",
        parser_version="sarasota.dispatch.v1",
        license_note="Synthetic records only. Never use as evidence of operational accuracy.",
        limitations="Synthetic records only; they are not evidence of operational accuracy.",
        contact_note="Test fixture for deterministic parser and replay tests.",
    )
    live_metadata = ProviderMetadata(
        provider_id="sarasota.official_dispatch",
        name="Sarasota County official dispatch reporting interface",
        source_authority="Sarasota County, Florida",
        geographic_coverage="Sarasota County, Florida",
        data_type="dispatch_snapshot",
        authentication_method="none_public_https_get",
        authorized_use_status=(
            "development_operator_authorized; recorded approval required outside development"
        ),
        enabled_by_default=settings.enable_live_sarasota_dispatch_polling,
        polling_interval_seconds=settings.sarasota_poll_interval_seconds,
        schema_version="sarasota.dispatch.schema.v1",
        parser_version="sarasota.dispatch.v1",
        license_note="Automated use remains subject to the source owner’s terms and the repository approval gate.",
        limitations="Normal HTTPS GET only. CAPTCHA/access controls/rate limits must not be bypassed. Live polling is 15-minute minimum and fails closed without approval.",
        contact_note="Production/staging require a recorded LegalApproval for live polling.",
    )
    property_fixture_metadata = ProviderMetadata(
        provider_id="fixture.sarasota.property_appraiser",
        name="Synthetic Sarasota property-appraiser fixture",
        source_authority="Synthetic fixture; not an external authority",
        geographic_coverage="Sarasota County, Florida (synthetic)",
        data_type="property_bulk_file",
        authentication_method="none",
        authorized_use_status="test_only",
        enabled_by_default=True,
        polling_interval_seconds=None,
        schema_version="sarasota.property.schema.v1",
        parser_version="sarasota.property.v1",
        license_note="Synthetic records only. Never use as evidence of property-match accuracy.",
        limitations="Synthetic records only; they are not evidence of real property data or matching accuracy.",
        contact_note="Test fixture for deterministic import, address, and matching tests.",
    )
    property_metadata = ProviderMetadata(
        provider_id="sarasota.property_appraiser",
        name="Sarasota County Property Appraiser bulk datasets",
        source_authority="Sarasota County Property Appraiser",
        geographic_coverage="Sarasota County, Florida",
        data_type="property_bulk_file",
        authentication_method="to_be_confirmed",
        authorized_use_status="authorization_required",
        enabled_by_default=False,
        polling_interval_seconds=None,
        schema_version="sarasota.property.schema.v1",
        parser_version="sarasota.property.v1",
        license_note="Source terms and authorized import use must be confirmed before operational use.",
        limitations="Manual/file import only; no automated retrieval is enabled; source versions and mappings must be retained.",
        contact_note="Written source approval and current field documentation required.",
    )
    return ProviderRegistry(
        providers={
            fixture_metadata.provider_id: FixtureProvider(fixture_metadata, fixture_path),
            live_metadata.provider_id: SarasotaDispatchProvider(live_metadata, settings),
            property_fixture_metadata.provider_id: FixtureProvider(
                property_fixture_metadata, property_fixture_path
            ),
            property_metadata.provider_id: SarasotaPropertyAppraiserProvider(property_metadata),
        }
    )


def fixture_is_well_formed(path: Path) -> bool:
    data = json.loads(path.read_text())
    return data.get("fixture_type") == "synthetic_dispatch_snapshot" and isinstance(
        data.get("records"), list
    )
