from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from app.db import get_db
from app.incidents.evidence import group_observations
from app.incidents.linkage import choose_linkage
from app.main import app
from app.models import CanonicalIncident, DispatchObservation, IncidentObservationLink
from app.providers.taxonomy import UNKNOWN_FIRE
from fastapi.testclient import TestClient
from scripts.repair_sarasota_duplicate_incidents import (
    _duplicate_key,
    _observations_match_key,
)
from sqlalchemy import select

from .test_auth import bootstrap


def _headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {bootstrap(client)}"}


def _upload_json(
    client: TestClient,
    headers: dict[str, str],
    records: list[dict[str, Any]],
    key: str,
    *,
    provider_id: str = "sarasota.official_dispatch",
):
    payload = json.dumps({"records": records}).encode()
    return client.post(
        f"/api/v1/providers/{provider_id}/snapshots",
        headers={**headers, "Idempotency-Key": key},
        files={"file": (f"{key}.json", payload, "application/json")},
        data={"authorized_snapshot": "true"},
    )


def _process(client: TestClient, headers: dict[str, str], retrieval_id: str):
    return client.post(f"/api/v1/incidents/process/retrievals/{retrieval_id}", headers=headers)


def test_sarasota_snapshot_processing_is_replay_idempotent(client: TestClient) -> None:
    headers = _headers(client)
    with open("apps/api/fixtures/sample_sarasota_dispatch.html", "rb") as snapshot:
        upload = client.post(
            "/api/v1/providers/sarasota.official_dispatch/snapshots",
            headers={**headers, "Idempotency-Key": "phase3-sarasota-current"},
            files={"file": ("current.html", snapshot, "text/html")},
            data={"authorized_snapshot": "true"},
        )
    assert upload.status_code == 201, upload.text
    retrieval_id = upload.json()["retrieval_id"]
    assert upload.json()["acquisition_mode"] == "manual_snapshot"

    first = _process(client, headers, retrieval_id)
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert first_body["new_incident_count"] >= 1
    assert first_body["classification_version"] == "incident-classification.v2"

    replay = _process(client, headers, retrieval_id)
    assert replay.status_code == 201, replay.text
    assert replay.json()["processing_run_id"] == first_body["processing_run_id"]
    assert replay.json()["new_incident_count"] == first_body["new_incident_count"]

    incidents = client.get(
        "/api/v1/incidents?provider_id=sarasota.official_dispatch", headers=headers
    )
    assert incidents.status_code == 200
    assert len(incidents.json()) == first_body["new_incident_count"]
    detail = client.get(f"/api/v1/incidents/{incidents.json()[0]['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["observations"]
    assert detail.json()["evidence_groups"]
    assert detail.json()["source_row_ids"]
    assert detail.json()["source_acquisition_modes"] == ["manual_snapshot"]
    assert detail.json()["relationship_history"]
    assert detail.json()["timeline"]


def test_incident_list_offset_exposes_rows_beyond_the_first_page(client: TestClient) -> None:
    headers = _headers(client)
    upload = _upload_json(
        client,
        headers,
        [
            {
                "event_datetime": "2026-07-31T09:00:00Z",
                "event_type": "PUBLIC SERVICE FIRE",
                "location": "588 BOUNDARY BLVD",
                "source_event_id": "E-PAGE-BOUNDARY",
            },
            {
                "event_datetime": "2026-07-31T10:00:00Z",
                "event_type": "STRUCTURE FIRE",
                "location": "589 BOUNDARY BLVD",
                "source_event_id": "E-PAGE-BOUNDARY-2",
            },
        ],
        "phase3-incident-list-pagination",
    )
    assert upload.status_code == 201, upload.text
    processed = _process(client, headers, upload.json()["retrieval_id"])
    assert processed.status_code == 201, processed.text

    first_page = client.get(
        "/api/v1/incidents?provider_id=sarasota.official_dispatch&offset=0&limit=1",
        headers=headers,
    )
    second_page = client.get(
        "/api/v1/incidents?provider_id=sarasota.official_dispatch&offset=1&limit=1",
        headers=headers,
    )
    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert first_page.json()[0]["canonical_location"] == "589 BOUNDARY BLVD"
    assert second_page.json()[0]["canonical_location"] == "588 BOUNDARY BLVD"


def test_replayed_processing_refreshes_stale_taxonomy_projection(client: TestClient) -> None:
    headers = _headers(client)
    upload = _upload_json(
        client,
        headers,
        [
            {
                "event_datetime": "2026-07-31T09:00:00Z",
                "event_type": "TRAFFIC CRASH W/INJURY",
                "location": "555 Replay Refresh Road, Sarasota, FL",
                "source_event_id": "E-REPLAY-TAXONOMY",
            }
        ],
        "phase3-replay-taxonomy-refresh",
    )
    assert upload.status_code == 201, upload.text
    retrieval_id = upload.json()["retrieval_id"]
    assert _process(client, headers, retrieval_id).status_code == 201
    incident = client.get(
        "/api/v1/incidents?provider_id=sarasota.official_dispatch", headers=headers
    ).json()[0]

    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        persisted = db.get(CanonicalIncident, incident["id"])
        assert persisted is not None
        persisted.classification_family = UNKNOWN_FIRE
        persisted.classification_version = "incident-classification.v1"
        observation_ids = db.scalars(
            select(IncidentObservationLink.observation_id).where(
                IncidentObservationLink.incident_id == persisted.id,
                IncidentObservationLink.is_current.is_(True),
            )
        ).all()
        for observation_id in observation_ids:
            observation = db.get(DispatchObservation, observation_id)
            assert observation is not None
            observation.normalized_event_family = UNKNOWN_FIRE
        db.commit()
    finally:
        db_generator.close()

    replay = _process(client, headers, retrieval_id)
    assert replay.status_code == 201, replay.text
    refreshed = client.get(f"/api/v1/incidents/{incident['id']}", headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["classification_family"] == "Traffic crash"


def test_concurrent_processing_reserves_one_run_and_one_assignment(client: TestClient) -> None:
    headers = _headers(client)
    upload = _upload_json(
        client,
        headers,
        [
            {
                "event_datetime": "2026-07-31T09:00:00Z",
                "event_type": "STRUCTURE FIRE",
                "location": "111 Safe Street, Sarasota, FL",
                "source_event_id": "E-CONCURRENT",
                "source_case_number": "C-CONCURRENT",
            }
        ],
        "phase3-concurrent-processing",
    )
    assert upload.status_code == 201, upload.text
    retrieval_id = upload.json()["retrieval_id"]

    def process_once(_value: int):
        return _process(client, headers, retrieval_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(process_once, [1, 2]))
    assert all(response.status_code == 201 for response in responses)
    assert len({response.json()["processing_run_id"] for response in responses}) == 1
    incidents = client.get(
        "/api/v1/incidents?provider_id=sarasota.official_dispatch", headers=headers
    )
    assert incidents.status_code == 200
    assert len(incidents.json()) == 1


def test_concurrent_cross_retrieval_duplicate_source_identity_is_one_incident(
    client: TestClient,
) -> None:
    headers = _headers(client)
    base_record = {
        "event_datetime": "2026-07-31T09:30:00Z",
        "event_type": "STRUCTURE FIRE",
        "location": "222 Same Source Lane, Sarasota, FL",
        "source_event_id": "E-CROSS-RETRIEVAL",
        "source_case_number": "C-CROSS-RETRIEVAL",
    }
    first = _upload_json(
        client,
        headers,
        [{**base_record, "grid": "G1"}],
        "phase3-cross-retrieval-1",
    )
    second = _upload_json(
        client,
        headers,
        [{**base_record, "grid": "G2"}],
        "phase3-cross-retrieval-2",
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    retrieval_ids = [first.json()["retrieval_id"], second.json()["retrieval_id"]]

    def process_once(retrieval_id: str):
        return _process(client, headers, retrieval_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(process_once, retrieval_ids))
    assert all(response.status_code == 201 for response in responses)
    incidents = client.get(
        "/api/v1/incidents?provider_id=sarasota.official_dispatch", headers=headers
    )
    assert incidents.status_code == 200
    assert len(incidents.json()) == 1
    assert incidents.json()[0]["observation_count"] == 2
    detail = client.get(f"/api/v1/incidents/{incidents.json()[0]['id']}", headers=headers)
    assert detail.status_code == 200
    detail_body = detail.json()
    assert len(detail_body["evidence_groups"]) == 1
    assert detail_body["evidence_groups"][0]["retained_observation_count"] == 2
    assert detail_body["evidence_groups"][0]["source_capture_count"] == 2


def test_source_identity_is_scoped_to_provider(client: TestClient) -> None:
    headers = _headers(client)
    record = {
        "event_datetime": "2026-07-31T08:00:00Z",
        "event_type": "STRUCTURE FIRE",
        "location": "333 Provider Boundary Road, Sarasota, FL",
        "source_event_id": "E-PROVIDER-SCOPE",
        "source_case_number": "C-PROVIDER-SCOPE",
    }
    official = _upload_json(client, headers, [record], "phase3-provider-official")
    fixture = _upload_json(
        client,
        headers,
        [{**record, "grid": "G2"}],
        "phase3-provider-fixture",
        provider_id="fixture.sarasota.dispatch",
    )
    assert official.status_code == 201, official.text
    assert fixture.status_code == 201, fixture.text
    assert _process(client, headers, official.json()["retrieval_id"]).status_code == 201
    assert _process(client, headers, fixture.json()["retrieval_id"]).status_code == 201
    official_incidents = client.get(
        "/api/v1/incidents?provider_id=sarasota.official_dispatch", headers=headers
    ).json()
    fixture_incidents = client.get(
        "/api/v1/incidents?provider_id=fixture.sarasota.dispatch", headers=headers
    ).json()
    assert len(official_incidents) == 1
    assert len(fixture_incidents) == 1


def test_shared_event_id_overrides_alternate_case_number_when_event_identity_agrees() -> None:
    event_time = datetime(2026, 7, 31, 10, tzinfo=timezone.utc)
    base = {
        "event_time": event_time,
        "original_location": "100 Main Street, Sarasota, FL",
        "source_event_id": "E-SHARED-EVENT",
        "agency": "SCFD",
        "normalized_event_family": "General structure fire",
        "original_event_type": "STRUCTURE FIRE",
        "grid": "G1",
        "station": "STA 1",
    }
    existing = SimpleNamespace(
        **base,
        source_record_id="record-1",
        source_case_number="SCFD-CASE-1",
    )
    alternate_case = SimpleNamespace(
        **base,
        source_record_id="record-2",
        source_case_number="SCFD-CASE-2",
    )

    choice = choose_linkage(alternate_case, [(SimpleNamespace(id="incident-1"), [existing])])

    assert choice.decision == "match"
    assert choice.stage == "deterministic"
    assert choice.explanation["reason"] == (
        "exact agency event identifier with compatible time and location"
    )


def test_reused_event_id_at_same_address_but_different_time_is_separate() -> None:
    existing = SimpleNamespace(
        event_time=datetime(2026, 7, 31, 10, tzinfo=timezone.utc),
        original_location="100 Main Street, Sarasota, FL",
        source_event_id="E-REUSED-SAME-ADDRESS",
        source_case_number="SCFD-CASE-1",
        source_record_id="record-1",
        agency="SCFD",
        normalized_event_family="General structure fire",
        original_event_type="STRUCTURE FIRE",
        grid="G1",
        station="STA 1",
    )
    later = SimpleNamespace(
        event_time=datetime(2026, 7, 31, 10, 30, tzinfo=timezone.utc),
        original_location="100 Main Street, Sarasota, FL",
        source_event_id="E-REUSED-SAME-ADDRESS",
        source_case_number="SCFD-CASE-2",
        source_record_id="record-2",
        agency="SCFD",
        normalized_event_family="General structure fire",
        original_event_type="STRUCTURE FIRE",
        grid="G1",
        station="STA 1",
    )

    choice = choose_linkage(later, [(SimpleNamespace(id="incident-1"), [existing])])

    assert choice.decision == "non_match"
    assert choice.stage == "deterministic_guard"
    assert choice.explanation["reason"] == "reused_source_event_id"


def test_exact_match_outranks_unrelated_reused_id_guard() -> None:
    new_observation = SimpleNamespace(
        event_time=datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc),
        original_location="1415 Brenner Park Drive, Sarasota, FL",
        source_event_id="EVENT-EXACT",
        source_case_number="CASE-EXACT",
        source_record_id="record-new",
        agency="SCFD",
        normalized_event_family="General structure fire",
        original_event_type="STRUCTURE FIRE",
        grid="G1",
        station="STA 1",
    )
    unrelated_observation = SimpleNamespace(
        event_time=datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc),
        original_location="425 US 41 BYP N, Sarasota, FL",
        source_event_id="EVENT-EXACT",
        source_case_number="CASE-OTHER",
        source_record_id="record-unrelated",
        agency="SCFD",
        normalized_event_family="General structure fire",
        original_event_type="STRUCTURE FIRE",
        grid="G2",
        station="STA 2",
    )
    exact_observation = SimpleNamespace(
        event_time=new_observation.event_time,
        original_location=new_observation.original_location,
        source_event_id=new_observation.source_event_id,
        source_case_number=new_observation.source_case_number,
        source_record_id="record-old",
        agency=new_observation.agency,
        normalized_event_family=new_observation.normalized_event_family,
        original_event_type=new_observation.original_event_type,
        grid=new_observation.grid,
        station=new_observation.station,
    )
    unrelated = SimpleNamespace(id="unrelated")
    exact = SimpleNamespace(id="exact")

    choice = choose_linkage(
        new_observation,
        [
            (unrelated, [unrelated_observation]),
            (exact, [exact_observation]),
        ],
    )

    assert choice.candidate is exact
    assert choice.decision == "match"


def test_same_case_event_update_within_conservative_window_remains_linked() -> None:
    existing = SimpleNamespace(
        event_time=datetime(2026, 7, 31, 10, tzinfo=timezone.utc),
        original_location="100 Main Street, Sarasota, FL",
        source_event_id="E-DELAYED-UPDATE",
        source_case_number="SCFD-CASE-1",
        source_record_id="record-1",
        agency="SCFD",
        normalized_event_family="General structure fire",
        original_event_type="STRUCTURE FIRE",
        grid="G1",
        station="STA 1",
    )
    update = SimpleNamespace(
        event_time=datetime(2026, 7, 31, 10, 6, tzinfo=timezone.utc),
        original_location="100 Main Street, Sarasota, FL",
        source_event_id="E-DELAYED-UPDATE",
        source_case_number="SCFD-CASE-1",
        source_record_id="record-2",
        agency="SCFD",
        normalized_event_family="General structure fire",
        original_event_type="STRUCTURE FIRE",
        grid="G1",
        station="STA 1",
    )

    choice = choose_linkage(update, [(SimpleNamespace(id="incident-1"), [existing])])

    assert choice.decision == "match"
    assert choice.stage == "deterministic"


def test_repeated_unchanged_source_captures_form_one_evidence_group() -> None:
    common = {
        "provider_id": "sarasota.official_dispatch",
        "source_event_id": "E-GROUPED",
        "event_time": datetime(2026, 7, 31, 10, tzinfo=timezone.utc),
        "original_event_type": "STRUCTURE FIRE",
        "normalized_event_family": "General structure fire",
        "original_location": "100 Main Street, Sarasota, FL",
    }
    first = SimpleNamespace(
        id="observation-1",
        source_record_id="record-1",
        raw_snapshot_id="snapshot-1",
        retrieved_at=datetime(2026, 7, 31, 10, 5, tzinfo=timezone.utc),
        **common,
    )
    second = SimpleNamespace(
        id="observation-2",
        source_record_id="record-2",
        raw_snapshot_id="snapshot-2",
        retrieved_at=datetime(2026, 7, 31, 10, 10, tzinfo=timezone.utc),
        **common,
    )
    changed = SimpleNamespace(
        id="observation-3",
        source_record_id="record-3",
        raw_snapshot_id="snapshot-3",
        retrieved_at=datetime(2026, 7, 31, 10, 15, tzinfo=timezone.utc),
        event_time=datetime(2026, 7, 31, 10, 6, tzinfo=timezone.utc),
        provider_id=common["provider_id"],
        source_event_id=common["source_event_id"],
        original_event_type="ALARM SOUNDING",
        normalized_event_family="Routine fire alarm",
        original_location=common["original_location"],
    )

    groups = group_observations([first, second, changed])

    assert [len(group.observations) for group in groups] == [2, 1]
    assert groups[0].representative.id == "observation-1"
    assert groups[0].source_record_ids == ["record-1", "record-2"]
    assert len(groups[0].source_snapshot_ids) == 2


def test_duplicate_repair_requires_every_observation_to_share_the_exact_key() -> None:
    first = SimpleNamespace(
        event_time=datetime(2026, 7, 31, 10, tzinfo=timezone.utc),
        original_location="100 Main Street, Sarasota, FL",
        source_event_id="E-REPAIR-KEY",
    )
    unrelated = SimpleNamespace(
        event_time=datetime(2026, 7, 31, 10, 1, tzinfo=timezone.utc),
        original_location="200 Pine Street, Sarasota, FL",
        source_event_id="E-REPAIR-KEY",
    )
    key = _duplicate_key("sarasota.official_dispatch", first)

    assert key is not None
    assert _observations_match_key("sarasota.official_dispatch", [first], key)
    assert not _observations_match_key("sarasota.official_dispatch", [first, unrelated], key)


def test_adversarial_deduplication_preserves_contradictions_and_separates_reused_ids(
    client: TestClient,
) -> None:
    headers = _headers(client)
    records = [
        {
            "event_datetime": "2026-07-31T10:00:00Z",
            "event_type": "STRUCTURE FIRE",
            "location": "100 Main Street, Sarasota, FL",
            "source_event_id": "E-DUP",
            "source_case_number": "C-DUP",
            "zone": "SCFD STA 1",
            "grid": "G1",
        },
        {
            "event_datetime": "2026-07-31T10:00:00Z",
            "event_type": "STRUCTURE FIRE",
            "location": "100 Main Street, Sarasota, FL",
            "source_event_id": "E-DUP",
            "source_case_number": "C-DUP",
            "zone": "SCFD STA 1",
            "grid": "G1",
        },
        {
            "event_datetime": "2026-07-31T10:05:00Z",
            "event_type": "ALARM SOUNDING",
            "location": "100 Main St, Sarasota, FL",
            "source_event_id": "E-DUP",
            "source_case_number": "C-DUP",
            "zone": "SCFD STA 1",
            "grid": "G1",
        },
        {
            "event_datetime": "2026-07-31T11:00:00Z",
            "event_type": "STRUCTURE FIRE",
            "location": "200 Pine Street, Sarasota, FL",
            "source_event_id": "E-REUSED",
            "source_case_number": "C-REUSED-1",
            "zone": "SCFD STA 2",
        },
        {
            "event_datetime": "2026-07-31T18:00:00Z",
            "event_type": "STRUCTURE FIRE",
            "location": "300 Oak Street, Sarasota, FL",
            "source_event_id": "E-REUSED",
            "source_case_number": "C-REUSED-2",
            "zone": "SCFD STA 2",
        },
        {
            "event_datetime": "2026-07-31T10:00:00Z",
            "event_type": "STRUCTURE FIRE",
            "location": "400 Palm Street, Sarasota, FL",
        },
        {
            "event_datetime": "2026-07-31T10:01:00Z",
            "event_type": "STRUCTURE FIRE",
            "location": "400 Palm St, Sarasota, FL",
        },
        {
            "event_datetime": "2026-07-31T12:00:00Z",
            "event_type": "STRUCTURE FIRE",
            "location": "600 Orange Avenue, Sarasota, FL",
            "source_event_id": "E-SEPARATE-1",
            "source_case_number": "C-SEPARATE-1",
            "zone": "SCFD STA 5",
        },
        {
            "event_datetime": "2026-07-31T15:00:00Z",
            "event_type": "STRUCTURE FIRE",
            "location": "600 Orange Ave, Sarasota, FL",
            "source_event_id": "E-SEPARATE-2",
            "source_case_number": "C-SEPARATE-2",
            "zone": "SCFD STA 5",
        },
        {"event_datetime": "2026-07-31T10:00:00Z", "location": "500 Bad Row, Sarasota, FL"},
    ]
    upload = _upload_json(client, headers, records, "phase3-adversarial")
    assert upload.status_code == 201, upload.text
    processed = _process(client, headers, upload.json()["retrieval_id"])
    assert processed.status_code == 201, processed.text

    incidents = client.get(
        "/api/v1/incidents?provider_id=sarasota.official_dispatch", headers=headers
    )
    assert incidents.status_code == 200
    rows = incidents.json()
    # Duplicate agency rows and missing-ID duplicates collapse; the reused identifier and
    # separate same-address/time-separated events remain distinct.
    assert len(rows) == 6
    all_details = [
        client.get(f"/api/v1/incidents/{row['id']}", headers=headers).json() for row in rows
    ]
    assert any(
        item["contradiction_count"] > 0
        and any(evidence["code"] == "conflicting_event_type" for evidence in item["evidence"])
        for item in all_details
    )
    decisions = [decision for item in all_details for decision in item["match_decisions"]]
    assert any(
        decision["decision"] == "non_match" and "reused" in decision["explanation"]["reason"]
        for decision in decisions
    )
    assert all(item["source_row_ids"] for item in all_details)


def test_incremental_update_rescores_and_manual_merge_split_are_audited(client: TestClient) -> None:
    headers = _headers(client)
    first = _upload_json(
        client,
        headers,
        [
            {
                "event_datetime": "2026-07-31T12:00:00Z",
                "event_type": "STRUCTURE FIRE",
                "location": "700 Bay Road, Sarasota, FL",
                "source_event_id": "E-INCREMENTAL",
                "source_case_number": "C-INCREMENTAL",
                "zone": "SCFD STA 3",
            }
        ],
        "phase3-incremental-1",
    )
    assert first.status_code == 201, first.text
    first_process = _process(client, headers, first.json()["retrieval_id"])
    assert first_process.status_code == 201, first_process.text
    first_list = client.get(
        "/api/v1/incidents?provider_id=sarasota.official_dispatch", headers=headers
    ).json()
    incident_id = first_list[0]["id"]

    second = _upload_json(
        client,
        headers,
        [
            {
                "event_datetime": "2026-07-31T12:04:00Z",
                "event_type": "ALARM SOUNDING",
                "location": "700 Bay Rd, Sarasota, FL",
                "source_event_id": "E-INCREMENTAL",
                "source_case_number": "C-INCREMENTAL",
                "zone": "SCFD STA 3",
            }
        ],
        "phase3-incremental-2",
    )
    assert second.status_code == 201, second.text
    second_process = _process(client, headers, second.json()["retrieval_id"])
    assert second_process.status_code == 201, second_process.text
    detail = client.get(f"/api/v1/incidents/{incident_id}", headers=headers).json()
    assert len(detail["observations"]) == 2
    assert detail["contradiction_count"] >= 1
    assert detail["classification_version"] == "incident-classification.v2"
    assert detail["review_signal_status"] == "revoked"
    assert any(item["event_type"] == "review_signal_revoked" for item in detail["timeline"])

    rescored = client.post(f"/api/v1/incidents/{incident_id}/rescore", headers=headers)
    assert rescored.status_code == 200, rescored.text
    assert any(item["event_type"] == "rescored" for item in rescored.json()["timeline"])

    third = _upload_json(
        client,
        headers,
        [
            {
                "event_datetime": "2026-07-31T20:00:00Z",
                "event_type": "STRUCTURE FIRE",
                "location": "900 Gulf Avenue, Sarasota, FL",
                "source_event_id": "E-MERGE",
                "source_case_number": "C-MERGE",
                "zone": "SCFD STA 4",
            }
        ],
        "phase3-merge-source",
    )
    assert third.status_code == 201, third.text
    assert _process(client, headers, third.json()["retrieval_id"]).status_code == 201
    separate = client.get(
        "/api/v1/incidents?provider_id=sarasota.official_dispatch", headers=headers
    ).json()
    absorbed_id = next(item["id"] for item in separate if item["id"] != incident_id)
    merged = client.post(
        f"/api/v1/incidents/{incident_id}/merge",
        headers=headers,
        json={"absorbed_incident_id": absorbed_id, "reason": "review confirmed same incident"},
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["observation_count"] == 3
    assert any(item["event_type"] == "merged" for item in merged.json()["timeline"])

    moved_observation_id = merged.json()["observations"][-1]["id"]
    split = client.post(
        f"/api/v1/incidents/{incident_id}/split",
        headers=headers,
        json={"observation_ids": [moved_observation_id], "reason": "review restored separate call"},
    )
    assert split.status_code == 200, split.text
    assert split.json()["observation_count"] == 1
    active_after_split = client.get(
        "/api/v1/incidents?provider_id=sarasota.official_dispatch", headers=headers
    ).json()
    assert len(active_after_split) == 2
    assert any(item["event_type"] == "split" for item in split.json()["timeline"])

    invalid = client.patch(
        f"/api/v1/incidents/{incident_id}/state",
        headers=headers,
        json={"state": "Invented approval state", "reason": "should fail"},
    )
    assert invalid.status_code == 422
    confirmed = client.patch(
        f"/api/v1/incidents/{incident_id}/state",
        headers=headers,
        json={"state": "Confirmed meaningful incident", "reason": "review confirmed evidence"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["state"] == "Confirmed meaningful incident"
