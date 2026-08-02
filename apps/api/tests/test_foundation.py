from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_explicitly_reports_phase_and_live_polling_state(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Beyond Fire Radar",
        "live_polling_enabled": False,
        "phase": "5-opportunity-scoring",
    }


def test_ready_check_uses_database(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
