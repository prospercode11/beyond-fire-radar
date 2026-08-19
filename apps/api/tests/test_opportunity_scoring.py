from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.db import get_db
from app.incidents.service import recompute_incident
from app.main import app
from app.models import (
    AuditEvent,
    CanonicalIncident,
    DispatchObservation,
    IncidentEvidence,
    IncidentObservationLink,
    OpportunityScoreRun,
)
from app.opportunities.scoring import (
    ADDRESS_FIX_SCORING_VERSION,
    BEYOND_ADJUSTING_FIT_PROFILE,
    CONTRADICTION_FIX_SCORING_VERSION,
    FIRE_ONLY_SCORING_VERSION,
    FIRE_SCOREABILITY_VERSION,
    PREVIOUS_FIRE_SCOREABILITY_VERSION,
    IncidentScoreSnapshot,
    PropertyScoreSnapshot,
    _fit,
    fire_score_eligibility,
    register_scoring_version,
    score_incident,
)
from app.providers.taxonomy import (
    EXTINGUISHED_FIRE,
    GENERAL_FIRE,
    GENERAL_STRUCTURE_FIRE,
    ILLEGAL_BURNING,
    PUBLIC_SERVICE_FIRE,
)
from fastapi.testclient import TestClient
from sqlalchemy import select


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
    matches = [item for item in incidents.json() if item["canonical_location"] == location]
    return min(
        matches,
        key=lambda item: (item["first_event_time"] or "9999-12-31T23:59:59Z", item["id"]),
    )["id"]


def test_sarasota_property_code_supplies_residential_fit_when_category_is_blank() -> None:
    fit = _fit(
        IncidentScoreSnapshot(
            classification_family=GENERAL_STRUCTURE_FIRE,
            classification_version="event-taxonomy.v1",
            classification_confidence=1.0,
            canonical_event_type="STRUCTURE FIRE",
            last_event_time=datetime(2026, 1, 15, 14, 22, tzinfo=timezone.utc),
            contradiction_count=0,
        ),
        PropertyScoreSnapshot(
            property_provider_id="sarasota.property_appraiser",
            property_use_code="0100",
            property_use_category=None,
            number_of_units=1,
            number_of_buildings=1,
            effective_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        ),
        rules={"beyond_adjusting_fit_profile": BEYOND_ADJUSTING_FIT_PROFILE},
    )

    assert fit.status == "available"
    assert fit.value == 1.0
    assert fit.evidence["property_segment"] == "residential"
    assert fit.evidence["property_segment_basis"] == "property_use_code"
    assert fit.evidence["property_code_source_url"] == "https://www.sc-pa.com/propertysearch/"


def test_sarasota_condominium_code_is_a_published_fit_segment() -> None:
    fit = _fit(
        IncidentScoreSnapshot(
            classification_family=GENERAL_STRUCTURE_FIRE,
            classification_version="event-taxonomy.v7",
            classification_confidence=1.0,
            canonical_event_type="GENERAL STRUCTURE FIRE",
            last_event_time=datetime(2026, 1, 15, 14, 22, tzinfo=timezone.utc),
            contradiction_count=0,
        ),
        PropertyScoreSnapshot(
            property_provider_id="sarasota.property_appraiser",
            property_use_code="0200",
            property_use_category=None,
            number_of_units=24,
            number_of_buildings=1,
            effective_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        ),
        rules={"beyond_adjusting_fit_profile": BEYOND_ADJUSTING_FIT_PROFILE},
    )

    assert fit.status == "available"
    assert fit.value == 1.0
    assert fit.evidence["property_segment"] == "condominium"


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
    assert data["scoring_version"] == "opportunity-scoring.v10"
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
    fit = next(item for item in data["features"] if item["feature_name"] == "beyond_adjusting_fit")
    assert fit["status"] == "available"
    assert fit["value"] < 1.0
    assert fit["evidence"]["proximity"]["proximity_status"] == "available"
    assert fit["evidence"]["proximity"]["distance_km"] > 0
    assert fit["evidence"]["property_segment"] == "residential"
    assert fit["evidence"]["claim_signal"] == "fire"
    assert fit["evidence"]["fit_inference"] is False
    assert fit["evidence"]["fit_profile_version"] == "beyondadjusting-fit.v4"
    assert fit["evidence"]["fit_source_url"] == "https://beyondadjusting.com/#claim"
    assert data["explanation"]["fit_profile_version"] == "beyondadjusting-fit.v4"
    assert data["explanation"]["evidence_group_count"] == 1
    assert data["explanation"]["retained_source_observation_count"] == 1
    versions = client.get("/api/v1/opportunities/scoring-versions", headers=headers)
    versions.raise_for_status()
    assert versions.json()[0]["version"] == "opportunity-scoring.v10"
    assert versions.json()[0]["rules"]["fire_scoreability"]["version"] == FIRE_SCOREABILITY_VERSION
    assert versions.json()[0]["rules"]["contradiction_projection"] == {
        "version": "incident-contradictions.v2",
        "current_grouped_evidence_only": True,
        "historical_evidence_retained": True,
    }


def test_v10_preserves_prior_scoring_releases_instead_of_mutating_them(
    client: TestClient,
) -> None:
    _auth(client)
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        previous = register_scoring_version(db, version_name=FIRE_ONLY_SCORING_VERSION)
        address_fix = register_scoring_version(db, version_name=ADDRESS_FIX_SCORING_VERSION)
        contradiction_fix = register_scoring_version(
            db, version_name=CONTRADICTION_FIX_SCORING_VERSION
        )
        current = register_scoring_version(db)
        assert previous.rules["fire_scoreability"]["version"] == (
            PREVIOUS_FIRE_SCOREABILITY_VERSION
        )
        assert PUBLIC_SERVICE_FIRE not in previous.rules["fire_scoreability"]["allowed_families"]
        assert address_fix.version == "opportunity-scoring.v8"
        assert "contradiction_projection" not in address_fix.rules
        assert contradiction_fix.version == "opportunity-scoring.v9"
        assert contradiction_fix.rules["contradiction_projection"]["version"] == (
            "incident-contradictions.v2"
        )
        assert current.version == "opportunity-scoring.v10"
        assert current.rules["fire_scoreability"]["version"] == FIRE_SCOREABILITY_VERSION
        assert PUBLIC_SERVICE_FIRE in current.rules["fire_scoreability"]["allowed_families"]
    finally:
        db.rollback()
        db_generator.close()


def test_current_release_uses_current_contradictions_without_erasing_historical_evidence(
    client: TestClient,
) -> None:
    headers = _auth(client)
    _import_property_fixture(client, headers)
    incident_id = _incident(
        client,
        headers,
        event_type="STRUCTURE FIRE",
        location="100 Example Avenue, Sarasota, FL 34236",
        key="score-stale-contradiction",
    )
    match = client.post(
        f"/api/v1/incidents/{incident_id}/property-matches",
        headers=headers,
        json={"property_provider_id": "fixture.sarasota.property_appraiser"},
    )
    match.raise_for_status()

    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        incident = db.get(CanonicalIncident, incident_id)
        observation = db.scalar(
            select(DispatchObservation)
            .join(
                IncidentObservationLink,
                IncidentObservationLink.observation_id == DispatchObservation.id,
            )
            .where(
                IncidentObservationLink.incident_id == incident_id,
                IncidentObservationLink.is_current.is_(True),
            )
        )
        assert incident is not None
        assert observation is not None
        historical = IncidentEvidence(
            id=str(uuid4()),
            incident_id=incident_id,
            observation_id=observation.id,
            evidence_type="contradictory",
            code="conflicting_event_type",
            summary="Historical contradiction retained after a taxonomy correction.",
            details={"historical": True},
        )
        db.add(historical)
        incident.contradiction_count = 1
        db.flush()

        old = score_incident(
            db,
            incident,
            property_provider_id="fixture.sarasota.property_appraiser",
            scoring_version=ADDRESS_FIX_SCORING_VERSION,
        )
        assert old.status == "abstained"
        assert old.abstention_reason == "contradictory_incident_evidence"

        assert recompute_incident(db, incident) == 0
        assert incident.contradiction_count == 0
        assert db.get(IncidentEvidence, historical.id) is historical

        current = score_incident(
            db,
            incident,
            property_provider_id="fixture.sarasota.property_appraiser",
        )
        assert current.scoring_version == "opportunity-scoring.v10"
        assert current.status == "scored"
        assert current.provisional_score is not None
    finally:
        db.rollback()
        db_generator.close()


def test_non_fire_crash_cannot_be_scored_or_listed_as_an_opportunity(
    client: TestClient,
) -> None:
    headers = _auth(client)
    incident_id = _incident(
        client,
        headers,
        event_type="TRAFFIC CRASH W/INJURY",
        location="501 N RIVER RD, Sarasota, FL 34236",
        key="score-traffic-crash",
    )

    detail = client.get(f"/api/v1/incidents/{incident_id}", headers=headers)
    detail.raise_for_status()
    assert detail.json()["classification_family"] == "Traffic crash"
    assert detail.json()["score_eligible"] is False
    assert "Traffic crash" in detail.json()["score_eligibility_reason"]

    response = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score",
        headers=headers,
        json={},
    )
    assert response.status_code == 422
    assert "explicit fire-related incidents" in response.json()["detail"]

    opportunities = client.get("/api/v1/opportunities", headers=headers)
    opportunities.raise_for_status()
    assert incident_id not in {item["incident_id"] for item in opportunities.json()}


def test_refresh_retires_a_current_score_after_non_fire_reclassification(
    client: TestClient,
) -> None:
    headers = _auth(client)
    incident_id = _incident(
        client,
        headers,
        event_type="STRUCTURE FIRE",
        location="404 Score Retirement Way, Sarasota, FL 34236",
        key="score-retirement",
    )
    created = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score",
        headers=headers,
        json={},
    )
    created.raise_for_status()

    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        observation = db.scalar(
            select(DispatchObservation)
            .join(
                IncidentObservationLink,
                IncidentObservationLink.observation_id == DispatchObservation.id,
            )
            .where(
                IncidentObservationLink.incident_id == incident_id,
                IncidentObservationLink.is_current.is_(True),
            )
        )
        assert observation is not None
        observation.original_event_type = "ROUTINE FIRE ALARM"
        db.commit()
    finally:
        db_generator.close()

    refreshed = client.post("/api/v1/opportunities/rescore-fire", headers=headers)
    refreshed.raise_for_status()
    assert refreshed.json()["rescored"] == 1
    opportunities = client.get("/api/v1/opportunities", headers=headers)
    opportunities.raise_for_status()
    assert incident_id not in {item["incident_id"] for item in opportunities.json()}

    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        current = db.scalar(
            select(OpportunityScoreRun).where(
                OpportunityScoreRun.incident_id == incident_id,
                OpportunityScoreRun.is_current.is_(True),
            )
        )
        assert current is None
        assert (
            db.scalar(
                select(AuditEvent).where(
                    AuditEvent.action == "opportunity.score_deactivated",
                    AuditEvent.resource_id == created.json()["id"],
                )
            )
            is not None
        )
    finally:
        db_generator.close()


def test_opportunity_list_offset_exposes_all_current_score_runs(client: TestClient) -> None:
    headers = _auth(client)
    incident_ids = [
        _incident(
            client,
            headers,
            event_type="FIRE",
            location=f"{number} Opportunity Paging Road, Sarasota, FL 34236",
            key=f"score-pagination-{number}",
        )
        for number in (101, 102)
    ]
    for incident_id in incident_ids:
        response = client.post(
            f"/api/v1/incidents/{incident_id}/opportunity-score",
            headers=headers,
            json={},
        )
        response.raise_for_status()

    first = client.get("/api/v1/opportunities?offset=0&limit=1", headers=headers)
    second = client.get("/api/v1/opportunities?offset=1&limit=1", headers=headers)
    first.raise_for_status()
    second.raise_for_status()
    assert len(first.json()) == 1
    assert len(second.json()) == 1
    assert first.json()[0]["incident_id"] != second.json()[0]["incident_id"]


def test_generic_fire_is_scoreable_without_being_promoted_to_structure_fire(
    client: TestClient,
) -> None:
    headers = _auth(client)
    incident_id = _incident(
        client,
        headers,
        event_type="FIRE",
        location="26700 BLOCK & SW 8TH ST, Miami-Dade, FL",
        key="score-generic-fire",
    )

    detail = client.get(f"/api/v1/incidents/{incident_id}", headers=headers)
    detail.raise_for_status()
    body = detail.json()
    assert body["classification_family"] == GENERAL_FIRE
    assert body["score_eligible"] is True

    response = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score",
        headers=headers,
        json={},
    )
    response.raise_for_status()
    assert response.json()["status"] == "abstained"
    assert response.json()["abstention_reason"] == "property_match_missing"


def test_source_specific_fire_families_are_scoreable() -> None:
    for family in (PUBLIC_SERVICE_FIRE, EXTINGUISHED_FIRE, ILLEGAL_BURNING):
        assert fire_score_eligibility(family) == (True, "")


def test_public_service_fire_is_scoreable_without_inventing_damage(
    client: TestClient,
) -> None:
    headers = _auth(client)
    incident_id = _incident(
        client,
        headers,
        event_type="PUBLIC SERVICE FIRE",
        location="588 BOUNDARY BLVD, Englewood, FL 34223",
        key="score-public-service-fire",
    )

    detail = client.get(f"/api/v1/incidents/{incident_id}", headers=headers)
    detail.raise_for_status()
    body = detail.json()
    assert body["classification_family"] == PUBLIC_SERVICE_FIRE
    assert body["score_eligible"] is True

    response = client.post(
        f"/api/v1/incidents/{incident_id}/opportunity-score",
        headers=headers,
        json={},
    )
    response.raise_for_status()
    assert response.json()["status"] == "abstained"
    assert response.json()["abstention_reason"] == "property_match_missing"


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
    assert later.json()["abstention_reason"] == "property_match_missing"

    boundary = client.post(
        f"/api/v1/incidents/{first_id}/opportunity-score/rescore",
        headers=headers,
        json={"as_of": datetime.now(timezone.utc).isoformat()},
    )
    boundary.raise_for_status()
    assert boundary.json()["abstention_reason"] == "property_match_missing"
    assert len(boundary.json()["source_observation_ids"]) == 1
