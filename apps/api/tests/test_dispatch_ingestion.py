from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.db import Base
from app.models import DispatchObservation, ImportJob, Provider, RawDispatchRow, RawSnapshot
from app.providers.ingestion import DispatchIngestionService
from app.providers.parsing import PARSER_VERSION, parse_snapshot
from app.providers.taxonomy import (
    GENERAL_STRUCTURE_FIRE,
    ROUTINE_FIRE_ALARM,
    TRAFFIC_CRASH_STRUCTURE,
    UNKNOWN_FIRE,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from .test_auth import bootstrap

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {bootstrap(client)}"}


def _upload(
    client: TestClient,
    headers: dict[str, str],
    *,
    provider_id: str,
    filename: str,
    content_type: str,
    payload: bytes,
    key: str,
    authorized_snapshot: bool = True,
):
    return client.post(
        f"/api/v1/providers/{provider_id}/snapshots",
        headers={**headers, "Idempotency-Key": key},
        files={"file": (filename, payload, content_type)},
        data={"authorized_snapshot": str(authorized_snapshot).lower()},
    )


def test_sarasota_html_parser_preserves_source_fields_and_taxonomy() -> None:
    result = parse_snapshot(
        _read("sample_sarasota_dispatch.html"), "text/html", "sample_sarasota_dispatch.html"
    )

    assert result.parser_version == PARSER_VERSION
    assert result.schema is not None
    assert result.schema.missing_required_fields == []
    assert len(result.rows) == 3
    assert result.issues == []
    assert result.rows[0].normalized_event_family == GENERAL_STRUCTURE_FIRE
    assert result.rows[1].normalized_event_family == ROUTINE_FIRE_ALARM
    assert result.rows[2].normalized_event_family == TRAFFIC_CRASH_STRUCTURE
    assert result.rows[0].source_case_number == "SCFD26040001"
    assert result.rows[0].source_event_id == "FR0726-50001"
    assert result.rows[0].agency == "SCFD"


def test_sarasota_csv_parser_handles_duplicate_event_headers() -> None:
    result = parse_snapshot(
        _read("sample_sarasota_dispatch.csv"), "text/csv", "sample_sarasota_dispatch.csv"
    )

    assert len(result.rows) == 3
    assert result.rows[1].source_event_id == "FR0726-50002"
    assert result.rows[1].original_event_type == "ALARM SOUNDING"


def test_json_event_datetime_satisfies_time_schema_requirement() -> None:
    result = parse_snapshot(
        b'{"records":[{"event_datetime":"2026-07-31T10:00:00Z","event_type":"STRUCTURE FIRE","location":"1 TEST WAY","source_event_id":"E-TEST"}]}',
        "application/json",
        "event-datetime.json",
    )

    assert result.schema is not None
    assert result.schema.missing_required_fields == []
    assert result.issues == []
    assert len(result.rows) == 1


def test_unknown_event_does_not_claim_fire_signal() -> None:
    result = parse_snapshot(
        b"Date,Time,Event,Location\n07/31/26,10:00,ODD CALL,1 TEST WAY\n",
        "text/csv",
        "unknown.csv",
    )

    assert result.rows[0].normalized_event_family == UNKNOWN_FIRE


def test_snapshot_upload_replay_and_raw_preservation(client: TestClient) -> None:
    headers = _headers(client)
    payload = _read("sample_sarasota_dispatch.html")

    denied = _upload(
        client,
        headers,
        provider_id="sarasota.official_dispatch",
        filename="approved.html",
        content_type="text/html",
        payload=payload,
        key="phase2-denied",
        authorized_snapshot=False,
    )
    assert denied.status_code == 403

    first = _upload(
        client,
        headers,
        provider_id="sarasota.official_dispatch",
        filename="approved.html",
        content_type="text/html",
        payload=payload,
        key="phase2-replay-1",
    )
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert first_body["status"] == "imported"
    assert first_body["normalized_record_count"] == 3
    assert first_body["replayed"] is False

    same_key = _upload(
        client,
        headers,
        provider_id="sarasota.official_dispatch",
        filename="approved.html",
        content_type="text/html",
        payload=payload,
        key="phase2-replay-1",
    )
    assert same_key.status_code == 201
    assert same_key.json()["replayed"] is True
    assert same_key.json()["import_job_id"] == first_body["import_job_id"]

    same_payload = _upload(
        client,
        headers,
        provider_id="sarasota.official_dispatch",
        filename="approved-again.html",
        content_type="text/html",
        payload=payload,
        key="phase2-replay-2",
    )
    assert same_payload.status_code == 201
    assert same_payload.json()["status"] == "replayed_existing_snapshot"
    assert same_payload.json()["replayed"] is True
    assert same_payload.json()["retrieval_id"] == first_body["retrieval_id"]

    conflict = _upload(
        client,
        headers,
        provider_id="sarasota.official_dispatch",
        filename="different.html",
        content_type="text/html",
        payload=_read("sample_sarasota_dispatch.csv"),
        key="phase2-replay-1",
    )
    assert conflict.status_code == 409

    observations = client.get(
        f"/api/v1/retrievals/{first_body['retrieval_id']}/observations", headers=headers
    )
    assert observations.status_code == 200
    assert len(observations.json()) == 3
    assert observations.json()[0]["raw_payload_reference"].startswith("local://")
    raw = client.get(f"/api/v1/retrievals/{first_body['retrieval_id']}/raw", headers=headers)
    assert raw.status_code == 200
    assert raw.content == payload

    health = client.get("/api/v1/providers/sarasota.official_dispatch/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["last_retrieval_status"] == "imported"
    assert health.json()["schema_drift_detected"] is False

    comparison = client.get(
        f"/api/v1/providers/sarasota.official_dispatch/parser-compare?retrieval_id={first_body['retrieval_id']}",
        headers=headers,
    )
    assert comparison.status_code == 200
    assert comparison.json()["normalized_record_count"] == 3


def test_parser_failure_and_zero_row_anomaly_are_visible(client: TestClient) -> None:
    headers = _headers(client)

    drift = _upload(
        client,
        headers,
        provider_id="sarasota.official_dispatch",
        filename="schema-drift.csv",
        content_type="text/csv",
        payload=_read("schema_drift_sarasota.csv"),
        key="phase2-schema-drift",
    )
    assert drift.status_code == 201
    drift_body = drift.json()
    assert drift_body["status"] == "parse_failed"
    assert drift_body["normalized_record_count"] == 0
    assert drift_body["schema_alert_count"] == 1

    errors = client.get(f"/api/v1/retrievals/{drift_body['retrieval_id']}/errors", headers=headers)
    assert errors.status_code == 200
    assert any(item["code"] == "schema_drift" for item in errors.json())
    alerts = client.get(
        f"/api/v1/retrievals/{drift_body['retrieval_id']}/schema-alerts", headers=headers
    )
    assert alerts.status_code == 200
    assert alerts.json()[0]["code"] == "missing_required_fields"

    zero = _upload(
        client,
        headers,
        provider_id="sarasota.official_dispatch",
        filename="zero-row.csv",
        content_type="text/csv",
        payload=_read("zero_row_sarasota.csv"),
        key="phase2-zero-row",
    )
    assert zero.status_code == 201
    zero_body = zero.json()
    assert zero_body["status"] == "zero_row_anomaly"
    assert zero_body["schema_alert_count"] == 1
    zero_errors = client.get(
        f"/api/v1/retrievals/{zero_body['retrieval_id']}/errors", headers=headers
    )
    assert any(item["code"] == "zero_row_anomaly" for item in zero_errors.json())


def test_concurrent_same_key_returns_one_retrieval(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    provider = Provider(
        id="sarasota.official_dispatch",
        name="Sarasota dispatch",
        source_authority="Sarasota County",
        geographic_coverage="Sarasota County",
        data_type="dispatch_snapshot",
        authentication_method="manual",
        authorized_use_status="authorization_required",
        enabled=False,
        polling_interval_seconds=None,
        schema_version="sarasota.dispatch.schema.v1",
        parser_version=PARSER_VERSION,
        license_note="test",
        limitations="test",
        contact_note="test",
    )
    with sessions() as db:
        db.add(provider)
        db.commit()

    settings = Settings(raw_snapshot_dir=str(tmp_path / "raw"))
    payload = _read("sample_sarasota_dispatch.html")

    def ingest_once(key: str, payload_value: bytes, filename: str, content_type: str):
        with sessions() as db:
            return DispatchIngestionService(settings).ingest(
                db,
                provider=db.get(Provider, provider.id),
                user_id="test-user",
                filename=filename,
                content_type=content_type,
                payload=payload_value,
                idempotency_key=key,
                authorized_snapshot=True,
                request_id=str(uuid4()),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        reports = list(
            executor.map(
                lambda args: ingest_once(*args),
                [
                    ("phase2-concurrent-key", payload, "concurrent.html", "text/html"),
                    ("phase2-concurrent-key", payload, "concurrent.html", "text/html"),
                ],
            )
        )

    assert sorted(report.replayed for report in reports) == [False, True]
    csv_payload = _read("sample_sarasota_dispatch.csv")
    with ThreadPoolExecutor(max_workers=2) as executor:
        hash_replay_reports = list(
            executor.map(
                lambda args: ingest_once(*args),
                [
                    ("phase2-concurrent-key-a", csv_payload, "concurrent.csv", "text/csv"),
                    ("phase2-concurrent-key-b", csv_payload, "concurrent.csv", "text/csv"),
                ],
            )
        )

    assert sorted(report.replayed for report in hash_replay_reports) == [False, True]
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ImportJob)) == 3
        assert db.scalar(select(func.count()).select_from(RawSnapshot)) == 2
        assert db.scalar(select(func.count()).select_from(RawDispatchRow)) == 6
        assert db.scalar(select(func.count()).select_from(DispatchObservation)) == 6
    engine.dispose()
