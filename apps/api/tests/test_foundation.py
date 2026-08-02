from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_explicitly_reports_phase_and_live_polling_state(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Beyond Fire Radar",
        "environment": "development",
        "live_polling_enabled": False,
        "live_polling_worker_enabled": False,
        "live_polling_interval_seconds": 900,
        "learned_model_serving_enabled": False,
        "phase": "10-production-hardening",
    }


def test_ready_check_uses_database(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
