from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.providers.base import Provider, ProviderMetadata, ProviderSnapshot


class ProviderDisabledError(RuntimeError):
    pass


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
    def __init__(self, metadata: ProviderMetadata, settings: Settings) -> None:
        self.metadata = metadata
        self.settings = settings

    def can_retrieve(self) -> bool:
        return (
            self.settings.enable_live_sarasota_dispatch_polling and self.metadata.enabled_by_default
        )

    def retrieve(self) -> ProviderSnapshot:
        raise ProviderDisabledError(
            "live Sarasota dispatch polling is disabled until written authorization and an approved integration exist"
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
        authentication_method="to_be_confirmed",
        authorized_use_status="authorization_required",
        enabled_by_default=False,
        polling_interval_seconds=None,
        schema_version="sarasota.dispatch.schema.v1",
        parser_version="sarasota.dispatch.v1",
        license_note="Terms and authorized automated use must be confirmed before activation.",
        limitations="CAPTCHA/access controls/rate limits must not be bypassed. Live polling is disabled; manual imports require an authorization attestation.",
        contact_note="Written approval and source documentation required.",
    )
    return ProviderRegistry(
        providers={
            fixture_metadata.provider_id: FixtureProvider(fixture_metadata, fixture_path),
            live_metadata.provider_id: SarasotaDispatchProvider(live_metadata, settings),
        }
    )


def fixture_is_well_formed(path: Path) -> bool:
    data = json.loads(path.read_text())
    return data.get("fixture_type") == "synthetic_dispatch_snapshot" and isinstance(
        data.get("records"), list
    )
