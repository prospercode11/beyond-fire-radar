from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import app.providers.polling as polling
import httpx
import pytest
from app.config import Settings
from app.db import Base
from app.models import (
    AuditEvent,
    CanonicalIncident,
    Provider,
    ProviderHealth,
    ProviderRetrieval,
    RawSnapshot,
    User,
)
from app.providers.polling import SarasotaPollingService
from app.providers.registry import build_registry
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

FIXTURES = Path(__file__).parents[1] / "fixtures"
PROVIDER_ID = "sarasota.official_dispatch"


def _database(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'polling.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as db:
        db.add(
            User(
                id="poller-user",
                email="poller@example.com",
                display_name="Polling User",
                password_hash="not-used",
            )
        )
        db.add(
            Provider(
                id=PROVIDER_ID,
                name="Sarasota dispatch",
                source_authority="Sarasota County",
                geographic_coverage="Sarasota County, Florida",
                data_type="dispatch_snapshot",
                authentication_method="none_public_https_get",
                authorized_use_status="development_operator_authorized",
                enabled=True,
                polling_interval_seconds=900,
                schema_version="sarasota.dispatch.schema.v1",
                parser_version="sarasota.dispatch.v1",
                license_note="test",
                limitations="test",
                contact_note="test",
            )
        )
        db.add(
            ProviderHealth(
                id=PROVIDER_ID,
                provider_id=PROVIDER_ID,
                known_status_note="test",
            )
        )
        db.commit()
    return engine, sessions


def _service(tmp_path: Path, *, settings: Settings | None = None):
    engine, sessions = _database(tmp_path)
    settings = settings or Settings(
        app_env="development",
        enable_live_sarasota_dispatch_polling=True,
        enable_sarasota_polling_worker=False,
        sarasota_live_authorization_basis="explicit_user_permission",
        raw_snapshot_dir=str(tmp_path / "raw"),
    )
    payload = (
        b"<!-- 911 Dispatch Reporting -->\n"
        + (FIXTURES / "sample_sarasota_dispatch.html").read_bytes()
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL(settings.sarasota_dispatch_url)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=payload,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    registry = build_registry(settings)
    registry.get(PROVIDER_ID).http_client = client
    return (
        SarasotaPollingService(
            settings,
            session_factory=sessions,
            registry=registry,
            owner=f"test:{uuid4()}",
        ),
        engine,
        sessions,
        client,
    )


def test_poll_fetches_processes_and_replays_without_duplicate_incidents(tmp_path: Path) -> None:
    service, engine, sessions, client = _service(tmp_path)
    try:
        first = service.poll_once()
        assert first.status == "retrieved"
        assert first.normalized_record_count == 3
        assert first.replayed is False
        second = service.poll_once()
        assert second.status == "replayed"
        assert second.replayed is True
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(ProviderRetrieval)) == 1
            assert db.scalar(select(func.count()).select_from(RawSnapshot)) == 1
            assert db.scalar(select(func.count()).select_from(CanonicalIncident)) == 3
    finally:
        client.close()
        engine.dispose()


def test_live_and_manual_identical_bytes_keep_distinct_provenance(tmp_path: Path) -> None:
    service, engine, sessions, client = _service(tmp_path)
    try:
        payload = (
            b"<!-- 911 Dispatch Reporting -->\n"
            + (FIXTURES / "sample_sarasota_dispatch.html").read_bytes()
        )
        with sessions() as db:
            provider = db.get(Provider, PROVIDER_ID)
            assert provider is not None
            from app.providers.ingestion import DispatchIngestionService

            manual = DispatchIngestionService(service.settings).ingest(
                db,
                provider=provider,
                user_id="poller-user",
                filename="manual.html",
                content_type="text/html",
                payload=payload,
                idempotency_key="manual-provenance-test",
                authorized_snapshot=True,
                request_id="manual-provenance-test",
            )
            assert manual.acquisition_mode == "manual_snapshot"
        live = service.poll_once()
        assert live.status == "retrieved"
        assert live.replayed is False
        with sessions() as db:
            modes = db.scalars(
                select(ProviderRetrieval.acquisition_mode).order_by(ProviderRetrieval.id)
            ).all()
            assert modes == ["live_poll", "manual_snapshot"] or modes == [
                "manual_snapshot",
                "live_poll",
            ]
            assert db.scalar(select(func.count()).select_from(RawSnapshot)) == 2
    finally:
        client.close()
        engine.dispose()


def test_next_poll_recovers_a_retained_snapshot_after_processing_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, engine, sessions, client = _service(tmp_path)
    original_process = polling.process_retrieval

    def fail_processing(*args, **kwargs):
        raise RuntimeError("simulated assembly failure")

    try:
        monkeypatch.setattr(polling, "process_retrieval", fail_processing)
        failed = service.poll_once()
        assert failed.status == "failed"
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(ProviderRetrieval)) == 1
            assert db.scalar(select(func.count()).select_from(RawSnapshot)) == 1
            assert db.scalar(select(func.count()).select_from(CanonicalIncident)) == 0
            health = db.get(ProviderHealth, PROVIDER_ID)
            assert health is not None
            assert health.last_retrieval_status == "poll_failed"

        monkeypatch.setattr(polling, "process_retrieval", original_process)
        recovered = service.poll_once()
        assert recovered.status == "replayed"
        assert recovered.recovered_retrieval_count == 1
        assert recovered.recovered_observation_count == 3
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(CanonicalIncident)) == 3
            health = db.get(ProviderHealth, PROVIDER_ID)
            assert health is not None
            assert health.failure_count == 0
            assert health.last_retrieval_status == "imported"
            events = db.scalars(
                select(AuditEvent.action).where(AuditEvent.action == "provider.retrieval_recovered")
            ).all()
            assert events == ["provider.retrieval_recovered"]
    finally:
        client.close()
        engine.dispose()


def test_poll_fails_closed_without_recorded_approval_outside_development(tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        enable_live_sarasota_dispatch_polling=True,
        enable_sarasota_polling_worker=True,
        raw_snapshot_dir=str(tmp_path / "raw"),
    )
    service, engine, sessions, client = _service(tmp_path, settings=settings)
    try:
        result = service.poll_once()
        assert result.status == "skipped"
        assert "LegalApproval" in result.reason
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(ProviderRetrieval)) == 0
            assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1
    finally:
        client.close()
        engine.dispose()


def test_poll_interval_is_exactly_fifteen_minutes() -> None:
    assert Settings().sarasota_poll_interval_seconds == 900
    with pytest.raises(ValueError):
        Settings(sarasota_poll_interval_seconds=899)
