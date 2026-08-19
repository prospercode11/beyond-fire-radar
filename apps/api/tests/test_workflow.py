from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.db import get_db
from app.main import app
from app.models import InternalAlert, NotificationJob, OpportunityScoreRun
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


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
    session = next(generator)
    return session, generator


def _fixture_incident(client: TestClient, headers: dict[str, str]) -> str:
    payload = json.dumps(
        {
            "records": [
                {
                    "source_record_id": "workflow-incident-1",
                    "source_event_id": "workflow-event-1",
                    "event_time": "2026-01-15T14:22:00Z",
                    "event_type": "STRUCTURE FIRE",
                    "location": "123 Workflow Way, Sarasota, FL 34236",
                }
            ]
        }
    ).encode()
    upload = client.post(
        "/api/v1/providers/fixture.sarasota.dispatch/snapshots",
        headers={**headers, "Idempotency-Key": "workflow-dispatch-1"},
        files={"file": ("workflow.json", payload, "application/json")},
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
    return next(
        item
        for item in incidents.json()
        if item["canonical_location"] == "123 Workflow Way, Sarasota, FL 34236"
    )["id"]


def _replace_current_score(db, incident_id: str) -> None:
    current = db.scalar(
        select(OpportunityScoreRun).where(
            OpportunityScoreRun.incident_id == incident_id,
            OpportunityScoreRun.is_current.is_(True),
        )
    )
    if current is not None:
        current.is_current = False
        db.flush()


def test_assignment_notes_and_existing_client_import_are_audited(client: TestClient) -> None:
    headers = _auth(client)
    incident_id = _fixture_incident(client, headers)

    assignment = client.post(
        f"/api/v1/workflow/incidents/{incident_id}/assignment",
        headers=headers,
        json={"assignee_user_id": None, "reason": "Keep unassigned pending reviewer triage."},
    )
    assignment.raise_for_status()
    assert assignment.json()["assignee_user_id"] is None

    note = client.post(
        f"/api/v1/workflow/incidents/{incident_id}/notes",
        headers=headers,
        json={"body": "Source wording retained for internal review.", "note_type": "evidence"},
    )
    note.raise_for_status()
    notes = client.get(f"/api/v1/workflow/incidents/{incident_id}/notes", headers=headers)
    notes.raise_for_status()
    assert notes.json()[0]["body"].startswith("Source wording")

    csv_payload = b"client_key,address,do_not_contact,source_note\nCLIENT-123,123 Workflow Way,yes,Existing internal client\n"
    imported = client.post(
        "/api/v1/workflow/clients/import",
        headers={**headers, "Idempotency-Key": "workflow-client-import-1"},
        files={"file": ("clients.csv", csv_payload, "text/csv")},
    )
    imported.raise_for_status()
    assert imported.json()["accepted_row_count"] == 1
    replayed = client.post(
        "/api/v1/workflow/clients/import",
        headers={**headers, "Idempotency-Key": "workflow-client-import-1"},
        files={"file": ("clients.csv", csv_payload, "text/csv")},
    )
    replayed.raise_for_status()
    assert replayed.json()["id"] == imported.json()["id"]
    clients = client.get("/api/v1/workflow/clients", headers=headers)
    clients.raise_for_status()
    assert clients.json()[0]["client_key"] == "CLIENT-123"

    audit = client.get("/api/v1/admin/audit", headers=headers)
    audit.raise_for_status()
    actions = {item["action"] for item in audit.json()}
    assert {
        "workflow.note.created",
        "workflow.client_import.created",
        "workflow.client_import.replayed",
    } <= actions


def test_alert_actions_are_append_audited_and_notification_delivery_is_internal_only(
    client: TestClient,
) -> None:
    headers = _auth(client)
    incident_id = _fixture_incident(client, headers)
    db, generator = _session()
    try:
        _replace_current_score(db, incident_id)
        score = OpportunityScoreRun(
            id=str(uuid4()),
            incident_id=incident_id,
            property_match_run_id=None,
            property_provider_id=None,
            scoring_version="opportunity-scoring.v1",
            previous_score_run_id=None,
            as_of=datetime(2026, 1, 15, 14, 22, tzinfo=timezone.utc),
            status="scored",
            provisional_score=82.0,
            evidence_tier="elite",
            alert_eligibility=True,
            abstention_reason=None,
            hard_gate_status="eligible_for_review",
            explanation={"semantics": "provisional evidence ranking, not an empirical probability"},
            source_observation_ids=[],
            available_at=None,
            created_by=None,
            is_current=True,
        )
        db.add(score)
        db.flush()
        alert = InternalAlert(
            id=str(uuid4()),
            incident_id=incident_id,
            score_run_id=score.id,
            dedupe_key=f"test:{incident_id}",
            alert_type="structure_review",
            severity="review",
            status="open",
            title="Internal review",
            summary="Internal-only review alert.",
            evidence_snapshot={"probability_display": False},
        )
        db.add(alert)
        db.flush()
        db.add(
            NotificationJob(id=str(uuid4()), alert_id=alert.id, channel="in_app", status="pending")
        )
        db.commit()
        alert_id = alert.id
    finally:
        generator.close()

    acknowledged = client.post(
        f"/api/v1/workflow/alerts/{alert_id}/acknowledge",
        headers=headers,
        json={"reason": "Reviewer accepted the internal queue item."},
    )
    acknowledged.raise_for_status()
    assert acknowledged.json()["status"] == "acknowledged"

    suppressed = client.post(
        f"/api/v1/workflow/alerts/{alert_id}/suppress",
        headers=headers,
        json={"reason": "Suppressed by internal review control."},
    )
    suppressed.raise_for_status()
    assert suppressed.json()["status"] == "suppressed"

    delivered = client.post("/api/v1/workflow/notifications/dispatch", headers=headers)
    delivered.raise_for_status()
    assert delivered.json()[0]["channel"] == "in_app"
    assert delivered.json()[0]["status"] == "suppressed"

    audit = client.get("/api/v1/admin/audit", headers=headers)
    audit.raise_for_status()
    actions = {item["action"] for item in audit.json()}
    assert {
        "workflow.alert.acknowledge",
        "workflow.alert.suppress",
        "workflow.notification.dispatched",
    } <= actions


def test_alert_generation_is_idempotent_and_fixture_scores_cannot_create_operational_alert(
    client: TestClient,
) -> None:
    headers = _auth(client)
    _fixture_incident(client, headers)
    first = client.post("/api/v1/workflow/alerts/generate", headers=headers)
    first.raise_for_status()
    second = client.post("/api/v1/workflow/alerts/generate", headers=headers)
    second.raise_for_status()
    assert first.json()["created_alerts"] == 0
    assert second.json()["created_alerts"] == 0
    alerts = client.get("/api/v1/workflow/alerts", headers=headers)
    alerts.raise_for_status()
    assert alerts.json() == []


def test_resolved_alert_notification_is_suppressed_not_delivered(client: TestClient) -> None:
    headers = _auth(client)
    incident_id = _fixture_incident(client, headers)
    db, generator = _session()
    try:
        _replace_current_score(db, incident_id)
        score = OpportunityScoreRun(
            id=str(uuid4()),
            incident_id=incident_id,
            scoring_version="opportunity-scoring.v1",
            as_of=datetime(2026, 1, 15, 14, 22, tzinfo=timezone.utc),
            status="scored",
            provisional_score=82.0,
            evidence_tier="elite",
            alert_eligibility=True,
            hard_gate_status="eligible_for_review",
            explanation={},
            source_observation_ids=[],
            is_current=True,
        )
        db.add(score)
        db.flush()
        alert = InternalAlert(
            id=str(uuid4()),
            incident_id=incident_id,
            score_run_id=score.id,
            dedupe_key=f"resolved-delivery:{incident_id}",
            alert_type="structure_review",
            severity="review",
            status="open",
            title="Internal review",
            summary="Internal-only review alert.",
            evidence_snapshot={},
        )
        db.add(alert)
        db.flush()
        db.add(NotificationJob(id=str(uuid4()), alert_id=alert.id, channel="in_app"))
        db.commit()
        alert_id = alert.id
    finally:
        generator.close()
    resolved = client.post(
        f"/api/v1/workflow/alerts/{alert_id}/resolve",
        headers=headers,
        json={"reason": "Resolved before in-app dispatch."},
    )
    resolved.raise_for_status()
    dispatched = client.post("/api/v1/workflow/notifications/dispatch", headers=headers)
    dispatched.raise_for_status()
    assert dispatched.json()[0]["status"] == "suppressed"


def test_alert_state_guards_escalation_terminal_states_and_unsuppress_rechecks(
    client: TestClient,
) -> None:
    headers = _auth(client)
    incident_id = _fixture_incident(client, headers)
    db, generator = _session()
    try:
        _replace_current_score(db, incident_id)
        score = OpportunityScoreRun(
            id=str(uuid4()),
            incident_id=incident_id,
            property_match_run_id=None,
            property_provider_id=None,
            scoring_version="opportunity-scoring.v1",
            previous_score_run_id=None,
            as_of=datetime(2026, 1, 15, 14, 22, tzinfo=timezone.utc),
            status="scored",
            provisional_score=82.0,
            evidence_tier="elite",
            alert_eligibility=True,
            abstention_reason=None,
            hard_gate_status="eligible_for_review",
            explanation={"semantics": "not a probability"},
            source_observation_ids=[],
            available_at=None,
            created_by=None,
            is_current=True,
        )
        db.add(score)
        db.flush()
        alert = InternalAlert(
            id=str(uuid4()),
            incident_id=incident_id,
            score_run_id=score.id,
            dedupe_key=f"guard:{incident_id}",
            alert_type="structure_review",
            severity="review",
            status="open",
            title="Internal review",
            summary="Internal-only review alert.",
            evidence_snapshot={"probability_display": False},
        )
        db.add(alert)
        db.commit()
        alert_id = alert.id
    finally:
        generator.close()

    escalated = client.post(
        f"/api/v1/workflow/alerts/{alert_id}/escalate",
        headers=headers,
        json={"reason": "Needs a second internal reviewer."},
    )
    escalated.raise_for_status()
    assert escalated.json()["status"] == "escalated"
    resolved = client.post(
        f"/api/v1/workflow/alerts/{alert_id}/resolve",
        headers=headers,
        json={"reason": "Escalation reviewed internally."},
    )
    resolved.raise_for_status()
    terminal_attempt = client.post(
        f"/api/v1/workflow/alerts/{alert_id}/acknowledge",
        headers=headers,
        json={"reason": "Must not reopen a resolved alert."},
    )
    assert terminal_attempt.status_code == 409

    db, generator = _session()
    try:
        score = db.scalar(select(OpportunityScoreRun).where(OpportunityScoreRun.id == alert_id))
        assert score is None
    finally:
        generator.close()


def test_suppressed_alert_cannot_be_reopened_when_fixture_evidence_is_ineligible(
    client: TestClient,
) -> None:
    headers = _auth(client)
    incident_id = _fixture_incident(client, headers)
    db, generator = _session()
    try:
        _replace_current_score(db, incident_id)
        score = OpportunityScoreRun(
            id=str(uuid4()),
            incident_id=incident_id,
            scoring_version="opportunity-scoring.v1",
            as_of=datetime(2026, 1, 15, 14, 22, tzinfo=timezone.utc),
            status="scored",
            provisional_score=82.0,
            evidence_tier="elite",
            alert_eligibility=True,
            hard_gate_status="eligible_for_review",
            explanation={},
            source_observation_ids=[],
            is_current=True,
        )
        db.add(score)
        db.flush()
        alert = InternalAlert(
            id=str(uuid4()),
            incident_id=incident_id,
            score_run_id=score.id,
            dedupe_key=f"unsuppress:{incident_id}",
            alert_type="structure_review",
            severity="review",
            status="open",
            title="Internal review",
            summary="Internal-only review alert.",
            evidence_snapshot={},
        )
        db.add(alert)
        db.commit()
        alert_id = alert.id
    finally:
        generator.close()
    suppressed = client.post(
        f"/api/v1/workflow/alerts/{alert_id}/suppress",
        headers=headers,
        json={"reason": "Fixture evidence remains non-operational."},
    )
    suppressed.raise_for_status()
    reopened = client.post(
        f"/api/v1/workflow/alerts/{alert_id}/unsuppress",
        headers=headers,
        json={"reason": "Attempted reopen without authorized manual evidence."},
    )
    assert reopened.status_code == 409


def test_notification_channel_is_database_guarded_to_in_app(client: TestClient) -> None:
    db, generator = _session()
    try:
        with pytest.raises(IntegrityError):
            db.add(
                NotificationJob(
                    id=str(uuid4()), alert_id="missing-alert", channel="email", status="pending"
                )
            )
            db.commit()
    finally:
        generator.close()
