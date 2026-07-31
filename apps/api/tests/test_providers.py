from __future__ import annotations

from app.config import get_settings
from app.providers.registry import ProviderDisabledError, SarasotaDispatchProvider, build_registry
from fastapi.testclient import TestClient

from .test_auth import bootstrap


def test_provider_registry_exposes_fixture_and_disabled_live_provider(client: TestClient) -> None:
    token = bootstrap(client)
    response = client.get("/api/v1/providers", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    providers = {item["id"]: item for item in response.json()["providers"]}
    assert providers["fixture.sarasota.dispatch"]["authorized_use_status"] == "test_only"
    assert providers["sarasota.official_dispatch"]["enabled"] is False


def test_live_provider_fails_closed() -> None:
    settings = get_settings()
    registry = build_registry(settings)
    provider = registry.get("sarasota.official_dispatch")
    assert isinstance(provider, SarasotaDispatchProvider)
    assert provider.can_retrieve() is False
    try:
        provider.retrieve()
    except ProviderDisabledError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("disabled live provider unexpectedly retrieved data")


def test_admin_can_disable_fixture_and_action_is_audited(client: TestClient) -> None:
    token = bootstrap(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/v1/providers/fixture.sarasota.dispatch/disable", headers=headers)
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    audit = client.get("/api/v1/admin/audit", headers=headers)
    assert audit.status_code == 200
    assert any(event["action"] == "provider.disabled" for event in audit.json())
