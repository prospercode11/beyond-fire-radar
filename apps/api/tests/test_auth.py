from __future__ import annotations

from fastapi.testclient import TestClient


def bootstrap(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "admin@example.com", "password": "development-password-123"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def test_bootstrap_login_and_me(client: TestClient) -> None:
    token = bootstrap(client)
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["roles"] == sorted(
        ["administrator", "licensed_adjuster", "analyst", "researcher", "read_only_reviewer"]
    )

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "development-password-123"},
    )
    assert login.status_code == 200


def test_bootstrap_is_one_time_and_invalid_credentials_are_rejected(client: TestClient) -> None:
    bootstrap(client)
    second = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "admin@example.com", "password": "development-password-123"},
    )
    assert second.status_code == 409
    invalid = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "wrong-password-123"},
    )
    assert invalid.status_code == 401


def test_protected_route_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/providers")
    assert response.status_code == 401
