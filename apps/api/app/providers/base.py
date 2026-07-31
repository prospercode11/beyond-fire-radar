from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class ProviderMetadata:
    provider_id: str
    name: str
    source_authority: str
    geographic_coverage: str
    data_type: str
    authentication_method: str
    authorized_use_status: str
    enabled_by_default: bool
    polling_interval_seconds: Optional[int]
    schema_version: str
    parser_version: str
    license_note: str
    limitations: str
    contact_note: str


@dataclass(frozen=True)
class ProviderSnapshot:
    provider_id: str
    content_type: str
    payload: bytes
    retrieved_at: str
    effective_at: Optional[str]


class Provider(Protocol):
    metadata: ProviderMetadata

    def can_retrieve(self) -> bool:
        """Return whether this provider is currently authorized and enabled."""

    def retrieve(self) -> ProviderSnapshot:
        """Retrieve one immutable snapshot or raise a structured provider error."""
