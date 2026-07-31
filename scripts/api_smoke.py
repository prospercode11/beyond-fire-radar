#!/usr/bin/env python3
"""Smoke-test the local API without requiring an external service."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx


def main() -> None:
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "change-me-in-development")

    with httpx.Client(base_url=base_url, timeout=5) as client:
        health = client.get("/healthz")
        health.raise_for_status()
        if health.json()["live_polling_enabled"]:
            raise RuntimeError("live polling must be disabled in the foundation smoke test")

        status = client.get("/api/v1/auth/bootstrap/status")
        status.raise_for_status()
        if status.json()["user_count"] == 0:
            created = client.post(
                "/api/v1/auth/bootstrap", json={"email": email, "password": password}
            )
            created.raise_for_status()

        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        providers = client.get("/api/v1/providers", headers=headers)
        providers.raise_for_status()
        if not providers.json()["providers"]:
            raise RuntimeError("provider registry is empty")

        me = client.get("/api/v1/auth/me", headers=headers)
        me.raise_for_status()
        if me.json()["email"] != email:
            raise RuntimeError("authenticated identity mismatch")

        snapshot_path = (
            Path(__file__).resolve().parents[1] / "apps/api/fixtures/sample_sarasota_dispatch.csv"
        )
        with snapshot_path.open("rb") as snapshot:
            upload = client.post(
                "/api/v1/providers/fixture.sarasota.dispatch/snapshots",
                headers={**headers, "Idempotency-Key": "api-smoke-phase2"},
                files={"file": (snapshot_path.name, snapshot, "text/csv")},
                data={"authorized_snapshot": "false"},
            )
        upload.raise_for_status()
        if upload.json()["normalized_record_count"] != 3:
            raise RuntimeError("dispatch snapshot did not produce the expected normalized rows")
        if upload.json()["acquisition_mode"] != "synthetic_fixture":
            raise RuntimeError("fixture ingestion was not labeled as synthetic input")

        before_incidents = client.get(
            "/api/v1/incidents?provider_id=fixture.sarasota.dispatch", headers=headers
        )
        before_incidents.raise_for_status()
        process = client.post(
            f"/api/v1/incidents/process/retrievals/{upload.json()['retrieval_id']}",
            headers=headers,
        )
        process.raise_for_status()
        after_incidents = client.get(
            "/api/v1/incidents?provider_id=fixture.sarasota.dispatch", headers=headers
        )
        after_incidents.raise_for_status()
        after_count = len(after_incidents.json())

        with snapshot_path.open("rb") as snapshot:
            replay = client.post(
                "/api/v1/providers/fixture.sarasota.dispatch/snapshots",
                headers={**headers, "Idempotency-Key": "api-smoke-phase2"},
                files={"file": (snapshot_path.name, snapshot, "text/csv")},
                data={"authorized_snapshot": "false"},
            )
        replay.raise_for_status()
        if not replay.json()["replayed"]:
            raise RuntimeError("dispatch snapshot replay was not reported")

        process_replay = client.post(
            f"/api/v1/incidents/process/retrievals/{replay.json()['retrieval_id']}",
            headers=headers,
        )
        process_replay.raise_for_status()
        final_incidents = client.get(
            "/api/v1/incidents?provider_id=fixture.sarasota.dispatch", headers=headers
        )
        final_incidents.raise_for_status()
        if len(final_incidents.json()) != after_count:
            raise RuntimeError("replaying a Sarasota fixture created duplicate canonical incidents")

    print("API smoke test passed")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
    main()
