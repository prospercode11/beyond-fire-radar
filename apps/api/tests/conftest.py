from __future__ import annotations

from pathlib import Path

import app.main as main_module
import pytest
from app.db import Base, get_db
from app.main import app
from app.providers.registry import fixture_is_well_formed
from app.rate_limit import limiter
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    limiter.reset()
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    test_engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(test_engine)

    def override_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(main_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "development-password-123")
    monkeypatch.setenv("RAW_SNAPSHOT_DIR", str(tmp_path / "raw-snapshots"))
    from app.config import get_settings

    get_settings.cache_clear()
    from app.api.routes.providers import seed_providers

    with TestingSessionLocal() as db:
        seed_providers(db)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    limiter.reset()
    get_settings.cache_clear()
    test_engine.dispose()


@pytest.fixture()
def fixture_path() -> Path:
    path = Path(__file__).parents[1] / "fixtures" / "sample_dispatch_snapshot.json"
    assert fixture_is_well_formed(path)
    return path
