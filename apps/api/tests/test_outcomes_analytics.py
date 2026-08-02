from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.db import get_db
from app.main import app
from app.models import InternalAlert
from fastapi.testclient import TestClient


def _auth(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "admin@example.com", "password": "development-password-123"},
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _session():
    override = app.dependency_overrides[get_db]
    generator = override()
    return next(generator), generator


def _fixture_incident(
    client: TestClient,
    headers: dict[str, str],
    *,
    key: str = "outcome-incident-1",
    location: str = "100 Example Avenue, Sarasota, FL 34236",
) -> str:
    payload = json.dumps(
        {
            "records": [
                {
                    "source_record_id": key,
                    "source_event_id": f"{key}-event",
                    "event_time": "2026-01-15T14:22:00Z",
                    "event_type": "STRUCTURE FIRE",
                    "location": location,
                }
            ]
        }
    ).encode()
    upload = client.post(
        "/api/v1/providers/fixture.sarasota.dispatch/snapshots",
        headers={**headers, "Idempotency-Key": f"{key}-dispatch"},
        files={"file": (f"{key}.json", payload, "application/json")},
        data={"authorized_snapshot": "false"},
    )
    upload.raise_for_status()
    processed = client.post(
        f"/api/v1/incidents/process/retrievals/{upload.json()['retrieval_id']}", headers=headers
    )
    processed.raise_for_status()
    incidents = client.get(
        "/api/v1/incidents?provider_id=fixture.sarasota.dispatch", headers=headers
    )
    incidents.raise_for_status()
    return next(item for item in incidents.json() if item["canonical_location"] == location)["id"]


def test_labels_events_and_reproducible_analytics_report(client: TestClient) -> None:
    headers = _auth(client)
    incident_id = _fixture_incident(client, headers)
    second_incident_id = _fixture_incident(
        client,
        headers,
        key="outcome-incident-2",
        location="101 Outcome Way, Sarasota, FL 34236",
    )

    property_path = (
        Path(__file__).parents[1] / "fixtures" / "sample_sarasota_property_appraiser.csv"
    )
    property_import = client.post(
        "/api/v1/properties/imports",
        headers=headers,
        files={"file": (property_path.name, property_path.read_bytes(), "text/csv")},
        data={
            "provider_id": "fixture.sarasota.property_appraiser",
            "source_version": "outcomes-property-2026-01",
            "idempotency_key": "outcomes-property-import-1",
            "import_mode": "full",
        },
    )
    property_import.raise_for_status()
    match = client.post(
        f"/api/v1/incidents/{incident_id}/property-matches",
        headers=headers,
        json={"property_provider_id": "fixture.sarasota.property_appraiser"},
    )
    match.raise_for_status()
    candidate_id = match.json()["candidates"][0]["id"]
    score = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score",
        headers=headers,
        json={"property_provider_id": "fixture.sarasota.property_appraiser"},
    )
    score.raise_for_status()
    property_decision = client.post(
        f"/api/v1/incidents/{incident_id}/property-matches/decisions",
        headers=headers,
        json={
            "decision": "confirmed",
            "candidate_id": candidate_id,
            "reason": "Confirmed for the labeled property-match evaluation case.",
        },
    )
    property_decision.raise_for_status()

    db, generator = _session()
    try:
        alert = InternalAlert(
            id=str(uuid4()),
            incident_id=incident_id,
            score_run_id=score.json()["id"],
            dedupe_key=f"outcomes:{incident_id}",
            alert_type="structure_review",
            severity="review",
            status="open",
            title="Internal review",
            summary="Internal-only evaluation alert.",
            evidence_snapshot={"fixture": True},
        )
        db.add(alert)
        db.commit()
        alert_id = alert.id
    finally:
        generator.close()

    relevant = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-labels",
        headers=headers,
        json={
            "label_type": "review_relevance",
            "label_value": "relevant",
            "rationale": "Manual reviewer marked the source record relevant for internal review.",
            "idempotency_key": "outcome-label-relevance-1",
        },
    )
    relevant.raise_for_status()
    replay = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-labels",
        headers=headers,
        json={
            "label_type": "review_relevance",
            "label_value": "relevant",
            "rationale": "Manual reviewer marked the source record relevant for internal review.",
            "idempotency_key": "outcome-label-relevance-1",
        },
    )
    replay.raise_for_status()
    assert replay.json()["id"] == relevant.json()["id"]
    conflict = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-labels",
        headers=headers,
        json={
            "label_type": "review_relevance",
            "label_value": "not_relevant",
            "error_category": "opportunity_ranking",
            "rationale": "Conflicting reuse must be rejected.",
            "idempotency_key": "outcome-label-relevance-1",
        },
    )
    assert conflict.status_code == 422

    property_label = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-labels",
        headers=headers,
        json={
            "label_type": "property_match",
            "label_value": "correct",
            "score_run_id": score.json()["id"],
            "property_match_run_id": match.json()["id"],
            "property_candidate_id": candidate_id,
            "property_decision_id": property_decision.json()["id"],
            "rationale": "The manual property review confirmed the predicted candidate.",
            "idempotency_key": "outcome-label-property-1",
        },
    )
    property_label.raise_for_status()
    useful = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-labels",
        headers=headers,
        json={
            "label_type": "alert_usefulness",
            "label_value": "useful",
            "alert_id": alert_id,
            "rationale": "The internal review queue item was useful to the reviewer.",
            "idempotency_key": "outcome-label-useful-1",
        },
    )
    useful.raise_for_status()

    occurred_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    for event_type, key in (
        ("review_completed", "outcome-event-review-1"),
        ("found_first", "outcome-event-found-first-1"),
    ):
        event = client.post(
            f"/api/v1/incidents/{incident_id}/outcome-events",
            headers=headers,
            json={
                "event_type": event_type,
                "occurred_at": occurred_at,
                "details": {"manual": True},
                "idempotency_key": key,
            },
        )
        event.raise_for_status()
    second_found_first = client.post(
        f"/api/v1/incidents/{second_incident_id}/outcome-events",
        headers=headers,
        json={
            "event_type": "found_first",
            "occurred_at": occurred_at,
            "idempotency_key": "outcome-event-found-first-only",
        },
    )
    second_found_first.raise_for_status()
    event_replay = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-events",
        headers=headers,
        json={
            "event_type": "review_completed",
            "occurred_at": occurred_at,
            "details": {"manual": True},
            "idempotency_key": "outcome-event-review-1",
        },
    )
    event_replay.raise_for_status()
    event_conflict = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-events",
        headers=headers,
        json={
            "event_type": "review_completed",
            "occurred_at": occurred_at,
            "details": {"manual": False},
            "idempotency_key": "outcome-event-review-1",
        },
    )
    assert event_conflict.status_code == 422

    outcomes = client.get(f"/api/v1/incidents/{incident_id}/outcomes", headers=headers)
    outcomes.raise_for_status()
    assert len(outcomes.json()["labels"]) == 3
    assert {item["event_type"] for item in outcomes.json()["events"]} == {
        "review_completed",
        "found_first",
    }

    report = client.post(
        "/api/v1/analytics/reports",
        headers=headers,
        json={
            "metrics": [
                "property_match_accuracy",
                "alert_usefulness",
                "found_first_rate",
                "reviewer_agreement",
                "error_taxonomy",
                "model_lab_readiness",
            ],
            "top_k": 5,
        },
    )
    report.raise_for_status()
    body = report.json()
    assert body["manifest"]["claim_status"] == "directional_only"
    assert body["manifest"]["source_acquisition_modes"] == ["synthetic_fixture"]
    assert body["manifest"]["source_retrieval_ids"]
    assert body["manifest"]["source_property_import_ids"]
    assert body["manifest"]["source_snapshot_hashes"]
    assert body["manifest"]["source_provenance"]["retrievals"]
    assert body["manifest"]["source_provenance"]["property_imports"]
    metrics = {item["metric_name"]: item for item in body["metrics"]}
    assert metrics["property_match_accuracy"]["value"] == 1.0
    assert metrics["property_match_accuracy"]["denominator"] == 1
    assert metrics["alert_usefulness"]["value"] == 1.0
    assert metrics["found_first_rate"]["value"] == 1.0
    assert metrics["found_first_rate"]["denominator"] == 1
    assert metrics["reviewer_agreement"]["status"] == "unavailable"
    assert metrics["error_taxonomy"]["details"]["counts"] == {}
    assert metrics["model_lab_readiness"]["status"] == "blocked"
    assert "synthetic fixture" in metrics["property_match_accuracy"]["warning"]

    fetched = client.get(f"/api/v1/analytics/reports/{body['manifest']['id']}", headers=headers)
    fetched.raise_for_status()
    assert fetched.json()["manifest"]["label_ids"] == body["manifest"]["label_ids"]
    replayed_report = client.post(
        f"/api/v1/analytics/reports/{body['manifest']['id']}/replay", headers=headers
    )
    replayed_report.raise_for_status()
    assert replayed_report.json() == body


def test_outcome_validation_rejects_unsupported_and_unexplained_negative_labels(
    client: TestClient,
) -> None:
    headers = _auth(client)
    incident_id = _fixture_incident(client, headers)
    missing_key = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-labels",
        headers=headers,
        json={
            "label_type": "review_relevance",
            "label_value": "relevant",
            "rationale": "An explicit idempotency key is required.",
        },
    )
    assert missing_key.status_code == 422
    missing_alert = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-labels",
        headers=headers,
        json={
            "label_type": "alert_usefulness",
            "label_value": "useful",
            "rationale": "Alert usefulness must identify the reviewed alert.",
            "idempotency_key": "outcome-missing-alert",
        },
    )
    assert missing_alert.status_code == 422
    missing_reason = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-labels",
        headers=headers,
        json={
            "label_type": "review_relevance",
            "label_value": "not_relevant",
            "rationale": "Not relevant without taxonomy.",
            "idempotency_key": "outcome-negative-missing-category",
        },
    )
    assert missing_reason.status_code == 422
    unbound_property = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-labels",
        headers=headers,
        json={
            "label_type": "property_match",
            "label_value": "correct",
            "rationale": "This must be bound to a predicted candidate and decision.",
            "idempotency_key": "outcome-unbound-property",
        },
    )
    assert unbound_property.status_code == 422
    future = client.post(
        f"/api/v1/incidents/{incident_id}/outcome-events",
        headers=headers,
        json={
            "event_type": "found_first",
            "occurred_at": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
            "idempotency_key": "outcome-future-event",
        },
    )
    assert future.status_code == 422
