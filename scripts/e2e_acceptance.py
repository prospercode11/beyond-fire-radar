#!/usr/bin/env python3
"""Exercise the governed v1 workflow against a running local API.

This intentionally uses repository fixtures. It verifies mechanics and source-mode
boundaries only; it is not evidence of source approval, accuracy, or conversion.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]


def body(response: httpx.Response) -> Any:
    if response.is_error:
        raise RuntimeError(f"{response.request.method} {response.request.url}: {response.text}")
    return response.json() if response.content else None


def main() -> None:
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "change-me-in-development")
    dispatch_path = ROOT / "apps/api/fixtures/sample_sarasota_dispatch.csv"
    property_path = ROOT / "apps/api/fixtures/sample_sarasota_property_appraiser.csv"

    with httpx.Client(base_url=base_url, timeout=10) as client:
        health = body(client.get("/healthz"))
        if health["live_polling_enabled"] or health["learned_model_serving_enabled"]:
            raise RuntimeError("live polling and learned serving must remain disabled")
        if client.get("/api/v1/incidents").status_code != 401:
            raise RuntimeError("incident reads must require authentication")

        bootstrap_status = body(client.get("/api/v1/auth/bootstrap/status"))
        if bootstrap_status["user_count"] == 0:
            token_response = body(
                client.post("/api/v1/auth/bootstrap", json={"email": email, "password": password})
            )
        else:
            token_response = body(
                client.post("/api/v1/auth/login", json={"email": email, "password": password})
            )
        headers = {"Authorization": f"Bearer {token_response['access_token']}"}

        with dispatch_path.open("rb") as dispatch_file:
            upload = body(
                client.post(
                    "/api/v1/providers/fixture.sarasota.dispatch/snapshots",
                    headers={**headers, "Idempotency-Key": "phase10-e2e-dispatch"},
                    files={"file": (dispatch_path.name, dispatch_file, "text/csv")},
                    data={"authorized_snapshot": "false"},
                )
            )
        body(
            client.post(
                f"/api/v1/incidents/process/retrievals/{upload['retrieval_id']}",
                headers=headers,
            )
        )
        incidents = body(
            client.get("/api/v1/incidents?provider_id=fixture.sarasota.dispatch", headers=headers)
        )
        incident = next(item for item in incidents if item["canonical_location"] == "123 MAIN ST")
        incident_id = incident["id"]
        before_replay_count = len(incidents)

        with dispatch_path.open("rb") as dispatch_file:
            replay = body(
                client.post(
                    "/api/v1/providers/fixture.sarasota.dispatch/snapshots",
                    headers={**headers, "Idempotency-Key": "phase10-e2e-dispatch"},
                    files={"file": (dispatch_path.name, dispatch_file, "text/csv")},
                    data={"authorized_snapshot": "false"},
                )
            )
        if not replay["replayed"]:
            raise RuntimeError("replay was not reported")
        body(
            client.post(
                f"/api/v1/incidents/process/retrievals/{replay['retrieval_id']}",
                headers=headers,
            )
        )
        after_replay = body(
            client.get("/api/v1/incidents?provider_id=fixture.sarasota.dispatch", headers=headers)
        )
        if len(after_replay) != before_replay_count:
            raise RuntimeError("replay created duplicate canonical incidents")

        detail = body(client.get(f"/api/v1/incidents/{incident_id}", headers=headers))
        for field in ("observations", "timeline", "match_decisions", "classification_explanation"):
            if not detail.get(field):
                raise RuntimeError(f"incident detail omitted governed {field} evidence")

        with property_path.open("rb") as property_file:
            body(
                client.post(
                    "/api/v1/properties/imports",
                    headers=headers,
                    files={"file": (property_path.name, property_file, "text/csv")},
                    data={
                        "provider_id": "fixture.sarasota.property_appraiser",
                        "source_version": "phase10-e2e-property",
                        "idempotency_key": "phase10-e2e-property-import",
                        "import_mode": "full",
                        "authorized_snapshot": "false",
                    },
                )
            )
        match = body(
            client.post(
                f"/api/v1/incidents/{incident_id}/property-matches",
                headers=headers,
                json={"property_provider_id": "fixture.sarasota.property_appraiser"},
            )
        )
        candidate_id = match["candidates"][0]["id"]
        score = body(
            client.post(
                f"/api/v1/incidents/{incident_id}/opportunity-score",
                headers=headers,
                json={"property_provider_id": "fixture.sarasota.property_appraiser"},
            )
        )
        if score["explanation"]["semantics"] != (
            "provisional evidence ranking, not an empirical probability"
        ):
            raise RuntimeError("score semantics boundary was not returned")
        decision = body(
            client.post(
                f"/api/v1/incidents/{incident_id}/property-matches/decisions",
                headers=headers,
                json={
                    "decision": "confirmed",
                    "candidate_id": candidate_id,
                    "reason": "Fixture-only mechanics confirmation; not accuracy evidence.",
                },
            )
        )
        if not decision["id"]:
            raise RuntimeError("property decision was not persisted")

        body(
            client.post(
                f"/api/v1/workflow/incidents/{incident_id}/assignment",
                headers=headers,
                json={"assignee_user_id": None, "reason": "Pending internal review."},
            )
        )
        body(
            client.post(
                f"/api/v1/workflow/incidents/{incident_id}/notes",
                headers=headers,
                json={
                    "body": "Fixture evidence retained for mechanics review.",
                    "note_type": "evidence",
                },
            )
        )
        client_payload = (
            b"client_key,address,do_not_contact,source_note\nE2E-1,123 MAIN ST,yes,fixture\n"
        )
        body(
            client.post(
                "/api/v1/workflow/clients/import",
                headers={**headers, "Idempotency-Key": "phase10-e2e-client-import"},
                files={"file": ("clients.csv", client_payload, "text/csv")},
            )
        )
        alert_result = body(
            client.post(
                "/api/v1/workflow/alerts/generate",
                params={"incident_id": incident_id},
                headers=headers,
            )
        )
        if alert_result["created_alerts"] != 0:
            raise RuntimeError("synthetic fixture data crossed the operational alert gate")

        body(
            client.post(
                f"/api/v1/incidents/{incident_id}/outcome-labels",
                headers=headers,
                json={
                    "label_type": "review_relevance",
                    "label_value": "relevant",
                    "rationale": "Fixture-only internal mechanics label.",
                    "idempotency_key": "phase10-e2e-outcome-label",
                },
            )
        )
        body(
            client.post(
                f"/api/v1/incidents/{incident_id}/outcome-events",
                headers=headers,
                json={
                    "event_type": "review_completed",
                    "occurred_at": datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc).isoformat(),
                    "idempotency_key": "phase10-e2e-outcome-event-v2",
                },
            )
        )
        report = body(
            client.post(
                "/api/v1/analytics/reports",
                headers=headers,
                json={"metrics": ["model_lab_readiness"], "top_k": 5},
            )
        )
        if report["manifest"]["claim_status"] != "directional_only":
            raise RuntimeError("fixture analytics did not retain its directional-only boundary")

        integrity = body(client.get("/api/v1/admin/audit/integrity", headers=headers))
        operations = body(client.get("/api/v1/admin/operations", headers=headers))
        if not integrity["valid"] or operations["database"] != "connected":
            raise RuntimeError("admin operational integrity checks failed")
        if "bfr_http_requests_total" not in client.get("/metrics").text:
            raise RuntimeError("metrics endpoint did not expose request metrics")

    print(
        "Phase 10 E2E acceptance passed: fixture-only mechanics, provenance, replay, review, workflow, outcomes, analytics, RBAC, and alert gate."
    )


if __name__ == "__main__":
    main()
