from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi.testclient import TestClient

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
    assert first_body["classification_version"] == "incident-classification.v1"

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
    assert detail.json()["source_row_ids"]
    assert detail.json()["source_acquisition_modes"] == ["manual_snapshot"]
    assert detail.json()["relationship_history"]
    assert detail.json()["timeline"]


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
    assert detail["classification_version"] == "incident-classification.v1"
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
