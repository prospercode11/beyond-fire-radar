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


class MiamiDadeProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BrowardProviderError(RuntimeError):
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


class MiamiDadeDispatchProvider:
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
            self.settings.enable_live_miami_dade_dispatch_polling
            and self.metadata.enabled_by_default
        )

    def retrieve(self) -> ProviderSnapshot:
        if not self.can_retrieve():
            raise ProviderDisabledError(
                "live Miami-Dade dispatch polling is disabled by configuration"
            )
        request_headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "BeyondFireRadar/0.1 (Miami-Dade public active-call polling)",
        }
        try:
            if self.http_client is not None:
                response = self.http_client.get(
                    self.settings.miami_dade_dispatch_url,
                    headers=request_headers,
                    timeout=self.settings.miami_dade_poll_timeout_seconds,
                )
            else:
                with httpx.Client(follow_redirects=True) as client:
                    response = client.get(
                        self.settings.miami_dade_dispatch_url,
                        headers=request_headers,
                        timeout=self.settings.miami_dade_poll_timeout_seconds,
                    )
        except httpx.HTTPError as exc:
            raise MiamiDadeProviderError(
                "network_error", f"Miami-Dade fire-call request failed: {exc}"
            ) from exc
        if response.status_code != 200:
            raise MiamiDadeProviderError(
                "http_error",
                f"Miami-Dade fire-call page returned HTTP {response.status_code}; no snapshot was imported",
            )
        payload = response.content
        if len(payload) > self.settings.max_snapshot_bytes:
            raise MiamiDadeProviderError(
                "snapshot_too_large",
                f"Miami-Dade fire-call response exceeds the configured {self.settings.max_snapshot_bytes} byte limit",
            )
        if b"MDFR CAD Active Calls" not in payload or b"<table" not in payload.lower():
            raise MiamiDadeProviderError(
                "unexpected_response",
                "Miami-Dade response did not contain the expected MDFR active-call tables",
            )
        return ProviderSnapshot(
            provider_id=self.metadata.provider_id,
            content_type=response.headers.get("content-type", "text/html; charset=utf-8"),
            payload=payload,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            effective_at=None,
        )


class MiamiDadePropertyAppraiserProvider:
    def __init__(self, metadata: ProviderMetadata) -> None:
        self.metadata = metadata

    def can_retrieve(self) -> bool:
        return False

    def retrieve(self) -> ProviderSnapshot:
        raise ProviderDisabledError(
            "automated Miami-Dade Property Appraiser retrieval is disabled; use an authorized file or the public parcel GIS download"
        )


class BrowardPropertyTaxRollProvider:
    def __init__(self, metadata: ProviderMetadata) -> None:
        self.metadata = metadata

    def can_retrieve(self) -> bool:
        return False

    def retrieve(self) -> ProviderSnapshot:
        raise ProviderDisabledError(
            "automated Broward property retrieval is disabled; use the operator-downloaded NAL/SDF/PIN files"
        )


class BrowardDispatchProvider:
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
            self.settings.enable_live_broward_dispatch_polling and self.metadata.enabled_by_default
        )

    def retrieve(self) -> ProviderSnapshot:
        if not self.can_retrieve():
            raise ProviderDisabledError(
                "live Broward dispatch polling is disabled by configuration"
            )
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "BeyondFireRadar/0.1 (Broward eFirstAlert polling)",
        }
        try:
            if self.http_client is not None:
                response = self.http_client.get(
                    self.settings.broward_dispatch_url,
                    headers=headers,
                    timeout=self.settings.broward_poll_timeout_seconds,
                )
            else:
                with httpx.Client(follow_redirects=True) as client:
                    response = client.get(
                        self.settings.broward_dispatch_url,
                        headers=headers,
                        timeout=self.settings.broward_poll_timeout_seconds,
                    )
        except httpx.HTTPError as exc:
            raise BrowardProviderError(
                "network_error", f"Broward eFirstAlert request failed: {exc}"
            ) from exc
        if response.status_code != 200:
            raise BrowardProviderError(
                "http_error",
                f"Broward eFirstAlert page returned HTTP {response.status_code}; no snapshot was imported",
            )
        payload = response.content
        if len(payload) > self.settings.max_snapshot_bytes:
            raise BrowardProviderError(
                "snapshot_too_large",
                f"Broward eFirstAlert response exceeds the configured {self.settings.max_snapshot_bytes} byte limit",
            )
        if b"Original Call Time" not in payload or b"Call Type" not in payload:
            raise BrowardProviderError(
                "unexpected_response",
                "Broward response did not contain the expected eFirstAlert dispatch table",
            )
        return ProviderSnapshot(
            provider_id=self.metadata.provider_id,
            content_type=response.headers.get("content-type", "text/html; charset=utf-8"),
            payload=payload,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            effective_at=None,
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
    miami_dispatch_metadata = ProviderMetadata(
        provider_id="miami_dade.fire_calls",
        name="Miami-Dade Fire Rescue active calls",
        source_authority="Miami-Dade County Fire Rescue",
        geographic_coverage="Miami-Dade County, Florida",
        data_type="dispatch_snapshot",
        authentication_method="none_public_https_get",
        authorized_use_status=(
            "development_operator_authorized; recorded approval required outside development"
        ),
        enabled_by_default=settings.enable_live_miami_dade_dispatch_polling,
        polling_interval_seconds=settings.miami_dade_poll_interval_seconds,
        schema_version="miami_dade.dispatch.schema.v1",
        parser_version="miami_dade.dispatch.v1",
        license_note="Public active-call display; automated use remains subject to county terms and the repository approval gate.",
        limitations=(
            "Active calls only, not a complete listing. RCVD is approximate, addresses may be blocks/cross-streets or general references, and initial incident information can change."
        ),
        contact_note="Source page: https://www.miamidade.gov/firecalls/calls.html",
    )
    miami_property_metadata = ProviderMetadata(
        provider_id="miami_dade.property_appraiser",
        name="Miami-Dade parcel, sales, and property-detail sources",
        source_authority="Miami-Dade Property Appraiser and Miami-Dade County GIS",
        geographic_coverage="Miami-Dade County, Florida",
        data_type="property_bulk_file",
        authentication_method="public_gis_or_property_appraiser_account",
        authorized_use_status="operator_supplied_file_or_public_gis",
        enabled_by_default=settings.enable_miami_dade_property_data,
        polling_interval_seconds=None,
        schema_version="miami_dade.property.schema.v1",
        parser_version="miami_dade.property.v1",
        license_note="Public parcel GIS is available from the county GIS service. Property Appraiser bulk CSVs require an authorized account and credits; no access controls are bypassed.",
        limitations=(
            "Manual/file import only. Public GIS parcel attributes and geometry do not substitute for complete paid sales or building-detail CSVs."
        ),
        contact_note=(
            "GIS: https://gisweb.miamidade.gov/arcgis/rest/services/Wasd/GovBound_8_v1/MapServer/0; bulk library: https://bbs.miamidade.gov/"
        ),
    )
    broward_dispatch_metadata = ProviderMetadata(
        provider_id="broward.efirstalert_dispatch",
        name="Broward County live dispatch via eFirstAlert",
        source_authority="eFirstAlert public dispatch aggregation; not an official Broward County dispatch record",
        geographic_coverage="Broward County, Florida",
        data_type="dispatch_snapshot",
        authentication_method="none_public_https_get",
        authorized_use_status="development_operator_authorized; recorded approval required outside development",
        enabled_by_default=settings.enable_live_broward_dispatch_polling,
        polling_interval_seconds=settings.broward_poll_interval_seconds,
        schema_version="broward.efirstalert.schema.v1",
        parser_version="broward.efirstalert.v1",
        license_note="Public third-party display; automated use remains subject to eFirstAlert terms and the repository approval gate.",
        limitations="Third-party public aggregation, not an official Broward County dispatch record. The page omits a stable incident ID and calendar date; call timestamps are date-inferred from retrieval. Mixed fire/medical, medical, crash, blank, and single-letter call types are retained but never treated as fire from units alone.",
        contact_note="Source page: https://efirstalert.com/live-dispatch-for-broward-county/",
    )
    broward_property_metadata = ProviderMetadata(
        provider_id="broward.property_tax_roll",
        name="Broward NAL, SDF, and PIN parcel sources",
        source_authority="Florida Department of Revenue Property Tax Data Portal",
        geographic_coverage="Broward County, Florida",
        data_type="property_bulk_file",
        authentication_method="public_https_download",
        authorized_use_status="operator_downloaded_manual_file",
        enabled_by_default=settings.enable_broward_property_data,
        polling_interval_seconds=None,
        schema_version="broward.property.schema.v1",
        parser_version="broward.property.v1",
        license_note="Downloaded public Florida Department of Revenue tax-roll and map files; retain source versions, hashes, and field mappings for every import.",
        limitations=(
            "Manual/file import only. NAL supplies tax-roll/property attributes, SDF supplies sales records, and PIN supplies parcel geometry; they must be joined by Broward parcel identifier. The 2025 preliminary NAL/SDF and 2025 final PIN are not a substitute for a current official title or building-detail search."
        ),
        contact_note="Florida DOR portal: https://floridarevenue.com/property/dataportal/",
    )
    return ProviderRegistry(
        providers={
            fixture_metadata.provider_id: FixtureProvider(fixture_metadata, fixture_path),
            live_metadata.provider_id: SarasotaDispatchProvider(live_metadata, settings),
            property_fixture_metadata.provider_id: FixtureProvider(
                property_fixture_metadata, property_fixture_path
            ),
            property_metadata.provider_id: SarasotaPropertyAppraiserProvider(property_metadata),
            miami_dispatch_metadata.provider_id: MiamiDadeDispatchProvider(
                miami_dispatch_metadata, settings
            ),
            miami_property_metadata.provider_id: MiamiDadePropertyAppraiserProvider(
                miami_property_metadata
            ),
            broward_dispatch_metadata.provider_id: BrowardDispatchProvider(
                broward_dispatch_metadata, settings
            ),
            broward_property_metadata.provider_id: BrowardPropertyTaxRollProvider(
                broward_property_metadata
            ),
        }
    )


def fixture_is_well_formed(path: Path) -> bool:
    data = json.loads(path.read_text())
    return data.get("fixture_type") == "synthetic_dispatch_snapshot" and isinstance(
        data.get("records"), list
    )
