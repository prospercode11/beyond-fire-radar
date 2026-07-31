from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4


class SnapshotStore(Protocol):
    def put(self, provider_id: str, content_hash: str, payload: bytes) -> str:
        """Persist immutable bytes and return a stable local/object reference."""

    def read(self, reference: str) -> bytes:
        """Read a previously persisted immutable snapshot."""


class LocalSnapshotStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, provider_id: str, content_hash: str, payload: bytes) -> str:
        safe_provider = provider_id.replace("/", "_").replace("..", "_")
        directory = self.root / safe_provider
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / content_hash
        if target.exists():
            existing = target.read_bytes()
            if hashlib.sha256(existing).hexdigest() != content_hash:
                raise ValueError("immutable snapshot path contains a different payload")
            return f"local://{safe_provider}/{content_hash}"

        temporary = directory / f".{content_hash}.{uuid4().hex}.partial"
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return f"local://{safe_provider}/{content_hash}"

    def read(self, reference: str) -> bytes:
        if reference.startswith("local://"):
            relative = reference.removeprefix("local://")
            provider_id, separator, content_hash = relative.partition("/")
            if not separator or not provider_id or len(content_hash) != 64:
                raise ValueError("invalid local snapshot reference")
            target = self.root / provider_id / content_hash
            if target.resolve().parent.parent != self.root.resolve():
                raise ValueError("snapshot reference escapes storage root")
            return target.read_bytes()
        return Path(reference).read_bytes()
