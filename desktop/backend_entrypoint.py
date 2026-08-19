"""Packaged FastAPI runner and update-safe SQLite backup helper."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional


def _bundle_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def _api_root() -> Path:
    return _bundle_root() / "apps" / "api"


def _backup_sqlite(source: Path, output: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".incomplete")
    if temporary.exists():
        temporary.unlink()
    try:
        source_db: Optional[sqlite3.Connection] = None
        target_db: Optional[sqlite3.Connection] = None
        try:
            source_db = sqlite3.connect(source, timeout=30)
            target_db = sqlite3.connect(temporary, timeout=30)
            source_db.backup(target_db)
        finally:
            if target_db is not None:
                target_db.close()
            if source_db is not None:
                source_db.close()
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def _migrate() -> None:
    api_root = _api_root()
    sys.path.insert(0, str(api_root))
    from alembic import command
    from alembic.config import Config

    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "migrations"))
    config.set_main_option("prepend_sys_path", str(api_root))
    command.upgrade(config, "head")


def _serve() -> None:
    api_root = _api_root()
    sys.path.insert(0, str(api_root))
    _migrate()
    import uvicorn
    from app.main import app

    uvicorn.run(
        app,
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "28741")),
        loop="asyncio",
        http="h11",
        access_log=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("serve")
    backup = subparsers.add_parser("backup")
    backup.add_argument("--database", type=Path, required=True)
    backup.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "serve":
        _serve()
    else:
        _backup_sqlite(args.database, args.output)


if __name__ == "__main__":
    main()
