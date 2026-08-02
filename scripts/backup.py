#!/usr/bin/env python3
"""Create, verify, and restore local backup bundles without exposing source payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import unquote
from uuid import uuid4


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("this local backup command expects a sqlite:/// DATABASE_URL")
    path = unquote(database_url[len(prefix) :])
    if not path or path == ":memory:":
        raise ValueError("an on-disk SQLite database is required for a backup")
    return Path(path).resolve()


def _copy_sqlite(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
        source_db.backup(target_db)


def _raw_relative_path(value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not value or value.startswith("/"):
        raise ValueError(f"unsafe raw payload path in backup manifest: {value}")
    return relative


def create_backup(database_url: str, output: Path, raw_dir: Optional[Path]) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not database_url.startswith("sqlite:///"):
        if output.suffix != ".dump":
            raise ValueError("PostgreSQL backups must use a .dump output path")
        subprocess.run(
            ["pg_dump", "--format=custom", "--file", str(output), database_url], check=True
        )
        print(json.dumps({"format": "postgresql-custom", "path": str(output)}))
        return

    source = _sqlite_path(database_url)
    if not source.exists():
        raise FileNotFoundError(source)
    with tempfile.TemporaryDirectory(prefix="bfr-backup-") as temporary:
        database_copy = Path(temporary) / "database.sqlite"
        _copy_sqlite(source, database_copy)
        manifest: dict[str, object] = {
            "format": "sqlite-bundle-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database_sha256": _sha256(database_copy),
            "raw_files": [],
        }
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(database_copy, "database.sqlite")
            if raw_dir and raw_dir.exists():
                root = raw_dir.resolve()
                raw_files: list[dict[str, str]] = []
                for path in sorted(root.rglob("*")):
                    if not path.is_file():
                        continue
                    if path.is_symlink() or root not in path.resolve().parents:
                        raise ValueError("raw snapshot directory contains an unsafe file")
                    relative = path.relative_to(root).as_posix()
                    archive.write(path, f"raw/{relative}")
                    raw_files.append({"path": relative, "sha256": _sha256(path)})
                manifest["raw_files"] = raw_files
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    print(json.dumps({"format": "sqlite-bundle-v1", "path": str(output), **manifest}))


def verify_backup(bundle: Path) -> None:
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        if "manifest.json" not in names or "database.sqlite" not in names:
            raise ValueError("backup bundle is missing its manifest or database")
        manifest = json.loads(archive.read("manifest.json"))
        with tempfile.TemporaryDirectory(prefix="bfr-backup-verify-") as temporary:
            database = Path(temporary) / "database.sqlite"
            database.write_bytes(archive.read("database.sqlite"))
            if _sha256(database) != manifest["database_sha256"]:
                raise ValueError("database checksum does not match the manifest")
            for item in manifest.get("raw_files", []):
                name = f"raw/{item['path']}"
                if name not in names:
                    raise ValueError(f"raw payload is missing from backup: {item['path']}")
                payload = Path(temporary) / "payload"
                payload.write_bytes(archive.read(name))
                if _sha256(payload) != item["sha256"]:
                    raise ValueError(f"raw payload checksum does not match: {item['path']}")
    print(json.dumps({"valid": True, "path": str(bundle)}))


def restore_backup(
    bundle: Path,
    target_database: Path,
    *,
    target_raw_dir: Optional[Path],
    force: bool,
) -> None:
    if target_database.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {target_database}; pass --force explicitly")
    with zipfile.ZipFile(bundle) as archive:
        verify_backup(bundle)
        manifest = json.loads(archive.read("manifest.json"))
        raw_files = manifest.get("raw_files", [])
        if raw_files and target_raw_dir is None:
            raise ValueError(
                "backup contains raw payloads; --target-raw-dir is required to restore them"
            )
        if target_raw_dir is not None and target_raw_dir.exists() and not force:
            raise FileExistsError(
                f"refusing to overwrite {target_raw_dir}; pass --force explicitly"
            )
        target_database.parent.mkdir(parents=True, exist_ok=True)
        temporary = target_database.with_suffix(target_database.suffix + ".restoring")
        raw_temporary: Optional[Path] = None
        if target_raw_dir is not None:
            target_raw_dir.parent.mkdir(parents=True, exist_ok=True)
            raw_temporary = (
                target_raw_dir.parent / f".{target_raw_dir.name}.restoring-{uuid4().hex}"
            )
        try:
            temporary.write_bytes(archive.read("database.sqlite"))
            if raw_temporary is not None:
                raw_temporary.mkdir(parents=True, exist_ok=False)
                for item in raw_files:
                    relative = _raw_relative_path(str(item["path"]))
                    target = raw_temporary / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    payload = archive.read(f"raw/{relative.as_posix()}")
                    if hashlib.sha256(payload).hexdigest() != item["sha256"]:
                        raise ValueError(f"raw payload checksum does not match: {relative}")
                    target.write_bytes(payload)
            if target_raw_dir is not None and target_raw_dir.exists():
                shutil.rmtree(target_raw_dir)
            if raw_temporary is not None and target_raw_dir is not None:
                os.replace(raw_temporary, target_raw_dir)
            os.replace(temporary, target_database)
        finally:
            if temporary.exists():
                temporary.unlink()
            if raw_temporary is not None and raw_temporary.exists():
                shutil.rmtree(raw_temporary)
    result: dict[str, object] = {"restored": True, "target": str(target_database)}
    if target_raw_dir is not None:
        result["raw_target"] = str(target_raw_dir)
        result["raw_file_count"] = len(raw_files)
    print(json.dumps(result))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "verify", "restore"])
    parser.add_argument(
        "--database-url", default=os.getenv("DATABASE_URL", "sqlite:///./data/beyond_fire_radar.db")
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--raw-dir", type=Path, default=None)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--target-database", type=Path)
    parser.add_argument(
        "--target-raw-dir",
        type=Path,
        help="directory receiving bundled raw payloads; required when the bundle contains them",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.action == "create":
        if args.output is None:
            parser.error("create requires --output")
        create_backup(args.database_url, args.output, args.raw_dir)
    elif args.action == "verify":
        if args.bundle is None:
            parser.error("verify requires --bundle")
        verify_backup(args.bundle)
    else:
        if args.bundle is None or args.target_database is None:
            parser.error("restore requires --bundle and --target-database")
        restore_backup(
            args.bundle,
            args.target_database,
            target_raw_dir=args.target_raw_dir,
            force=args.force,
        )


if __name__ == "__main__":
    main()
