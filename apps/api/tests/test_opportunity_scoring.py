from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


def _auth(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "admin@example.com", "password": "development-password-123"},
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _import_property_fixture(client: TestClient, headers: dict[str, str]) -> None:
    path = Path(__file__).parents[1] / "fixtures" / "sample_sarasota_property_appraiser.csv"
    response = client.post(
        "/api/v1/properties/imports",
        headers=headers,
        files={"file": (path.name, path.read_bytes(), "text/csv")},
        data={
            "provider_id": "fixture.sarasota.property_appraiser",
            "source_version": "fixture-scoring-2026-01",
            "idempotency_key": "scoring-property-import-001",
            "import_mode": "full",
        },
    )
    response.raise_for_status()


def _incident(
    client: TestClient,
    headers: dict[str, str],
    *,
    event_type: str,
    location: str,
    key: str,
    event_time: str = "2026-01-15T14:22:00Z",
) -> str:
    payload = json.dumps(
        {
            "records": [
                {
                    "source_record_id": key,
                    "source_event_id": f"EVENT-{key}",
                    "event_time": event_time,
                    "event_type": event_type,
                    "location": location,
                }
            ]
        }
    ).encode()
    upload = client.post(
        "/api/v1/providers/fixture.sarasota.dispatch/snapshots",
        headers={**headers, "Idempotency-Key": f"dispatch-{key}"},
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


def test_structure_score_is_versioned_explainable_and_not_a_probability(
    client: TestClient,
) -> None:
    headers = _auth(client)
    _import_property_fixture(client, headers)
    incident_id = _incident(
        client,
        headers,
        event_type="STRUCTURE FIRE",
        location="100 Example Avenue, Sarasota, FL 34236",
        key="score-structure",
    )
    match = client.post(
        f"/api/v1/incidents/{incident_id}/property-matches",
        headers=headers,
        json={"property_provider_id": "fixture.sarasota.property_appraiser"},
    )
    match.raise_for_status()
    response = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score",
        headers=headers,
        json={"property_provider_id": "fixture.sarasota.property_appraiser"},
    )
    response.raise_for_status()
    data = response.json()
    assert data["scoring_version"] == "opportunity-scoring.v1"
    assert data["provisional_score"] is not None
    assert data["alert_eligibility"] is False
    assert (
        data["explanation"]["semantics"]
        == "provisional evidence ranking, not an empirical probability"
    )
    assert {item["feature_name"] for item in data["features"]} >= {
        "source_quality",
        "incident_validity",
        "property_match_quality",
        "material_loss_evidence",
        "loss_complexity",
        "beyond_adjusting_fit",
        "data_sufficiency",
    }
    versions = client.get("/api/v1/opportunities/scoring-versions", headers=headers)
    versions.raise_for_status()
    assert versions.json()[0]["version"] == "opportunity-scoring.v1"


def test_negative_event_and_missing_property_abstain_without_top_opportunity(
    client: TestClient,
) -> None:
    headers = _auth(client)
    incident_id = _incident(
        client,
        headers,
        event_type="VEHICLE FIRE",
        location="800 PALM DR, Venice, FL 34293",
        key="score-vehicle",
    )
    response = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score",
        headers=headers,
        json={},
    )
    response.raise_for_status()
    data = response.json()
    assert data["status"] == "suppressed"
    assert data["evidence_tier"] == "suppressed"
    assert data["abstention_reason"] == "negative_source_relevance"
    assert data["alert_eligibility"] is False


def test_override_survives_rescore_and_score_rollback_restores_history(
    client: TestClient,
) -> None:
    headers = _auth(client)
    _import_property_fixture(client, headers)
    incident_id = _incident(
        client,
        headers,
        event_type="STRUCTURE FIRE",
        location="100 Example Avenue, Sarasota, FL 34236",
        key="score-override",
    )
    match = client.post(
        f"/api/v1/incidents/{incident_id}/property-matches",
        headers=headers,
        json={"property_provider_id": "fixture.sarasota.property_appraiser"},
    )
    match.raise_for_status()
    first = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score",
        headers=headers,
        json={"property_provider_id": "fixture.sarasota.property_appraiser"},
    )
    first.raise_for_status()
    override = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score/decisions",
        headers=headers,
        json={"decision": "suppress", "reason": "Human reviewer is holding this record."},
    )
    override.raise_for_status()
    assert override.json()["evidence_tier"] == "suppressed"
    second = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score/rescore",
        headers=headers,
        json={"property_provider_id": "fixture.sarasota.property_appraiser"},
    )
    second.raise_for_status()
    assert second.json()["human_override"]["decision"] == "suppress"
    rollback = client.post(f"/api/v1/opportunities/{second.json()['id']}/rollback", headers=headers)
    rollback.raise_for_status()
    assert rollback.json()["is_current"] is True
    assert rollback.json()["id"] == first.json()["id"]


def test_score_as_of_excludes_observations_retrieved_after_boundary(client: TestClient) -> None:
    headers = _auth(client)
    incident_id = _incident(
        client,
        headers,
        event_type="STRUCTURE FIRE",
        location="900 FUTURE DATA WAY, Sarasota, FL 34236",
        key="score-as-of",
    )
    before_retrieval = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    before = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score",
        headers=headers,
        json={"as_of": before_retrieval},
    )
    before.raise_for_status()
    assert before.json()["abstention_reason"] == "property_match_missing"
    assert before.json()["explanation"]["component_weights"]

    after_retrieval = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    after = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score/rescore",
        headers=headers,
        json={"as_of": after_retrieval},
    )
    after.raise_for_status()
    source_feature = next(
        item for item in after.json()["features"] if item["feature_name"] == "source_quality"
    )
    assert source_feature["status"] == "available"


def test_admin_can_register_a_non_probability_scoring_release(client: TestClient) -> None:
    headers = _auth(client)
    request = {
        "version": "opportunity-scoring.test-release",
        "component_versions": {
            "source_quality": "test.v1",
            "incident_validity": "test.v1",
            "property_match_quality": "test.v1",
            "material_loss_evidence": "test.v1",
            "loss_complexity": "test.v1",
            "beyond_adjusting_fit": "test.v1",
            "data_sufficiency": "test.v1",
        },
        "priors": {
            "source_quality": 0.15,
            "incident_validity": 0.20,
            "property_match_quality": 0.20,
            "material_loss_evidence": 0.15,
            "loss_complexity": 0.10,
            "beyond_adjusting_fit": 0.10,
            "data_sufficiency": 0.10,
        },
        "rules": {"negative_source_terms": ["alarm"], "probability_display": False},
        "description": "Test release for registry and rollback contract coverage.",
    }
    response = client.post("/api/v1/opportunities/scoring-versions", headers=headers, json=request)
    response.raise_for_status()
    assert response.json()["version"] == request["version"]


def test_historical_score_uses_boundary_incident_state_not_later_wording(
    client: TestClient,
) -> None:
    headers = _auth(client)
    base_time = datetime.now(timezone.utc)
    location = "901 TEMPORAL FIRE WAY, Sarasota, FL 34236"
    first_id = _incident(
        client,
        headers,
        event_type="STRUCTURE FIRE",
        location=location,
        key="score-temporal-first",
        event_time=(base_time - timedelta(minutes=15)).isoformat(),
    )
    second_id = _incident(
        client,
        headers,
        event_type="STRUCTURE FIRE ALARM",
        location=location,
        key="score-temporal-later",
        event_time=(base_time + timedelta(minutes=15)).isoformat(),
    )
    assert second_id == first_id

    later = client.post(
        f"/api/v1/incidents/{first_id}/opportunity-score",
        headers=headers,
        json={"as_of": (base_time + timedelta(days=1)).isoformat()},
    )
    later.raise_for_status()
    assert later.json()["abstention_reason"] == "negative_source_relevance"

    boundary = client.post(
        f"/api/v1/incidents/{first_id}/opportunity-score/rescore",
        headers=headers,
        json={"as_of": datetime.now(timezone.utc).isoformat()},
    )
    boundary.raise_for_status()
    assert boundary.json()["abstention_reason"] == "property_match_missing"
    assert len(boundary.json()["source_observation_ids"]) == 1
