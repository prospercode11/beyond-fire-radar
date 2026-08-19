from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import Settings
from app.db import Base
from app.providers.approval import live_polling_decision
from desktop.backend_entrypoint import _backup_sqlite
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_desktop_update_backup_is_consistent_and_keeps_source(tmp_path: Path) -> None:
    source = tmp_path / "alerts.db"
    backup = tmp_path / "backups" / "pre-update.sqlite"
    with sqlite3.connect(source) as database:
        database.execute("CREATE TABLE alerts (id INTEGER PRIMARY KEY, address TEXT NOT NULL)")
        database.execute("INSERT INTO alerts (address) VALUES ('11704 ALTAMONTE CT')")
        database.commit()

    _backup_sqlite(source, backup)

    assert source.is_file()
    with sqlite3.connect(backup) as database:
        assert database.execute("SELECT address FROM alerts").fetchone() == ("11704 ALTAMONTE CT",)


def test_desktop_local_operator_authorization_still_requires_exact_basis() -> None:
    allowed = Settings(
        app_env="desktop",
        enable_live_sarasota_dispatch_polling=True,
        sarasota_live_authorization_basis="explicit_user_permission",
    )
    denied = Settings(
        app_env="desktop",
        enable_live_sarasota_dispatch_polling=True,
        sarasota_live_authorization_basis="unverified",
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as database:
            assert live_polling_decision(database, allowed).allowed is True
            decision = live_polling_decision(database, denied)
            assert decision.allowed is False
            assert "LegalApproval" in decision.reason
    finally:
        engine.dispose()
