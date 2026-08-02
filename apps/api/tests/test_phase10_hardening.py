from __future__ import annotations

import io
import sqlite3
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

import pytest
from app.audit import record_audit, verify_audit_chain
from app.config import Settings, get_settings
from app.db import Base
from app.properties.importers import parse_property_file
from app.providers.storage import LocalSnapshotStore, S3SnapshotStore
from app.rate_limit import limiter
from fastapi.testclient import TestClient
from pydantic import ValidationError


def _token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "admin@example.com", "password": "development-password-123"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def test_security_headers_metrics_and_authenticated_audit_integrity(client: TestClient) -> None:
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["phase"] == "10-production-hardening"
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    assert health.headers["Content-Security-Policy"].startswith("default-src")
    assert health.headers["X-Request-ID"]

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    assert "bfr_http_requests_total" in metrics_response.text

    token = _token(client)
    integrity = client.get(
        "/api/v1/admin/audit/integrity", headers={"Authorization": f"Bearer {token}"}
    )
    assert integrity.status_code == 200, integrity.text
    assert integrity.json()["valid"] is True
    assert integrity.json()["event_count"] >= 1


def test_audit_chain_detects_tampering(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        record_audit(
            db,
            action="test.created",
            resource_type="test",
            resource_id="1",
            actor_user_id=None,
            request_id="test-request",
            metadata={"safe": True},
        )
        db.commit()
        assert verify_audit_chain(db).valid is True
        from app.models import AuditEvent

        stored = db.query(AuditEvent).one()
        stored.event_metadata = {"safe": False}
        db.commit()
        result = verify_audit_chain(db)
        assert result.valid is False
        assert result.reason == "audit event hash mismatch"
    engine.dispose()


def test_rate_limit_rejects_repeated_auth_attempts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_login_requests", 2)
    limiter.reset()
    for _ in range(2):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "unknown@example.com", "password": "development-password-123"},
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": "development-password-123"},
    )
    assert limited.status_code == 429
    assert limited.headers["Retry-After"]


def test_rate_limit_is_bounded_under_concurrency() -> None:
    settings = Settings()
    settings.rate_limit_login_requests = 10
    limiter.reset()

    def attempt() -> bool:
        try:
            limiter.check(scope="test", key="same-client", limit=10, settings=settings)
        except Exception:
            return False
        return True

    with ThreadPoolExecutor(max_workers=32) as pool:
        accepted = list(pool.map(lambda _: attempt(), range(100)))
    assert sum(accepted) == 10
    limiter.reset()


def test_health_latency_and_object_storage_integrity() -> None:
    settings = Settings(object_storage_bucket="bucket", object_storage_prefix="snapshots")

    class Body:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def read(self) -> bytes:
            return self.payload

    class FakeS3:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, Body]:
            if Key not in self.objects:
                error = RuntimeError("missing")
                error.response = {"Error": {"Code": "NoSuchKey"}}  # type: ignore[attr-defined]
                raise error
            return {"Body": Body(self.objects[Key])}

        def put_object(self, *, Bucket: str, Key: str, Body: bytes, **_: object) -> None:
            self.objects[Key] = Body if isinstance(Body, bytes) else bytes(Body)

        def delete_object(self, *, Bucket: str, Key: str) -> None:
            self.objects.pop(Key, None)

    payload = b"approved manual bytes are not implied by this mechanics test"
    content_hash = sha256(payload).hexdigest()
    store = S3SnapshotStore(settings, client=FakeS3())
    reference = store.put("manual.sarasota.dispatch", content_hash, payload)
    assert store.read(reference) == payload
    store.client.objects[reference.removeprefix("s3://bucket/")] = b"tampered"
    with pytest.raises(ValueError, match="immutable hash"):
        store.read(reference)


def test_upload_latency_budget(client: TestClient) -> None:
    import time

    started = time.perf_counter()
    for _ in range(100):
        response = client.get("/healthz")
        assert response.status_code == 200
    assert time.perf_counter() - started < 3.0


def test_upload_and_archive_boundaries_are_fail_closed(tmp_path: Path) -> None:
    store = LocalSnapshotStore(tmp_path / "storage")
    payload = b"immutable local payload"
    content_hash = sha256(payload).hexdigest()
    reference = store.put("fixture.sarasota.dispatch", content_hash, payload)
    stored = tmp_path / "storage" / "fixture.sarasota.dispatch" / content_hash
    stored.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="immutable hash"):
        store.read(reference)
    with pytest.raises(ValueError):
        store.read("/tmp/escape")
    with pytest.raises(ValueError):
        store.read("local://../escape/" + "a" * 64)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.csv", "parcel_id,address\n1,1 MAIN ST\n")
    parsed = parse_property_file(archive.getvalue(), "application/zip", "property.zip")
    assert parsed.format == "unknown"
    assert parsed.issues[0].code == "parse_failed"


def test_production_settings_reject_insecure_defaults() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production")
    secure = Settings(
        app_env="production",
        database_url="postgresql+psycopg://user:pass@db/app",
        web_origin="https://app.example.invalid",
        allowed_hosts="api.example.invalid",
        bootstrap_admin_password="a-secure-placeholder-that-is-not-the-default",
        enable_bootstrap=False,
        rate_limit_backend="redis",
        redis_required_for_readiness=True,
        raw_snapshot_backend="s3",
        object_storage_bucket="bucket",
        object_storage_endpoint_url="https://storage.example.invalid",
        object_storage_access_key_id="access-key",
        object_storage_secret_access_key="secret-key",
        enable_api_docs=False,
    )
    assert secure.enable_api_docs is False


def test_sqlite_backup_verify_and_restore(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    restored = tmp_path / "restored.db"
    raw_source = tmp_path / "raw-source"
    raw_source.mkdir()
    (raw_source / "sarasota").mkdir()
    (raw_source / "sarasota" / "payload.sha256").write_bytes(b"raw payload")
    restored_raw = tmp_path / "raw-restored"
    with sqlite3.connect(source) as db:
        db.execute("create table sample (value text not null)")
        db.execute("insert into sample values ('preserved')")
        db.commit()
    bundle = tmp_path / "backup.zip"
    subprocess.run(
        [
            sys.executable,
            "scripts/backup.py",
            "create",
            "--database-url",
            f"sqlite:///{source}",
            "--raw-dir",
            str(raw_source),
            "--output",
            str(bundle),
        ],
        check=True,
    )
    subprocess.run(
        [sys.executable, "scripts/backup.py", "verify", "--bundle", str(bundle)], check=True
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/backup.py",
            "restore",
            "--bundle",
            str(bundle),
            "--target-database",
            str(restored),
            "--target-raw-dir",
            str(restored_raw),
        ],
        check=True,
    )
    with sqlite3.connect(restored) as db:
        assert db.execute("select value from sample").fetchone() == ("preserved",)
    assert (restored_raw / "sarasota" / "payload.sha256").read_bytes() == b"raw payload"


def test_retention_failure_leaves_pending_tombstone_for_retry(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    from app.models import AuditEvent, RawSnapshot
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    database = tmp_path / "retention.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        db.add(
            RawSnapshot(
                id="raw-retention-1",
                provider_id="provider-1",
                retrieval_id="retrieval-1",
                content_hash="a" * 64,
                content_type="application/json",
                payload_reference="local://provider-1/" + "a" * 64,
                byte_size=10,
                created_at=datetime.now(timezone.utc) - timedelta(days=400),
            )
        )
        db.commit()

    import importlib.util

    retention_spec = importlib.util.spec_from_file_location(
        "phase10_retention", Path("scripts/retention.py")
    )
    assert retention_spec is not None and retention_spec.loader is not None
    retention = importlib.util.module_from_spec(retention_spec)
    retention_spec.loader.exec_module(retention)

    monkeypatch.setattr(retention, "SessionLocal", sessions)

    class FailingStore:
        def delete(self, reference: str) -> None:
            raise OSError("object store unavailable")

    assert (
        retention._purge_record(
            RawSnapshot,
            "raw-retention-1",
            store=FailingStore(),
            request_id="retention-test",
            days=365,
        )
        == "failed"
    )
    with sessions() as db:
        stored = db.get(RawSnapshot, "raw-retention-1")
        assert stored is not None
        assert stored.payload_purge_pending_at is not None
        assert stored.payload_purged_at is None
        assert (
            db.query(AuditEvent).filter_by(action="retention.raw_payload_purge_failed").count() == 1
        )

    class WorkingStore:
        def delete(self, reference: str) -> None:
            return None

    assert (
        retention._purge_record(
            RawSnapshot,
            "raw-retention-1",
            store=WorkingStore(),
            request_id="retention-test-retry",
            days=365,
        )
        == "purged"
    )
    with sessions() as db:
        stored = db.get(RawSnapshot, "raw-retention-1")
        assert stored is not None
        assert stored.payload_purge_pending_at is None
        assert stored.payload_purged_at is not None
        assert db.query(AuditEvent).filter_by(action="retention.raw_payload_purged").count() == 1
