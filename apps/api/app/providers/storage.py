from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Optional, Protocol
from uuid import uuid4

from app.config import Settings


class SnapshotStore(Protocol):
    def put(self, provider_id: str, content_hash: str, payload: bytes) -> str:
        """Persist immutable bytes and return a stable local/object reference."""

    def put_file(self, provider_id: str, content_hash: str, path: Path) -> str:
        """Persist an immutable file without materializing it in memory."""

    def read(self, reference: str) -> bytes:
        """Read a previously persisted immutable snapshot."""

    def delete(self, reference: str) -> None:
        """Delete payload bytes while retaining the database provenance tombstone."""


class LocalSnapshotStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, provider_id: str, content_hash: str, payload: bytes) -> str:
        _validate_content_hash(content_hash)
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

    def put_file(self, provider_id: str, content_hash: str, path: Path) -> str:
        _validate_content_hash(content_hash)
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != content_hash:
            raise ValueError("source file failed its immutable hash check")
        safe_provider = provider_id.replace("/", "_").replace("..", "_")
        directory = self.root / safe_provider
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / content_hash
        if target.exists():
            existing_digest = hashlib.sha256()
            with target.open("rb") as existing:
                for chunk in iter(lambda: existing.read(1024 * 1024), b""):
                    existing_digest.update(chunk)
            if existing_digest.hexdigest() != content_hash:
                raise ValueError("immutable snapshot path contains a different payload")
            return f"local://{safe_provider}/{content_hash}"
        temporary = directory / f".{content_hash}.{uuid4().hex}.partial"
        try:
            with path.open("rb") as source, temporary.open("xb") as destination:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    destination.write(chunk)
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
            _validate_content_hash(content_hash)
            if target.is_symlink() or target.resolve().parent.parent != self.root.resolve():
                raise ValueError("snapshot reference escapes storage root")
            payload = target.read_bytes()
            if hashlib.sha256(payload).hexdigest() != content_hash:
                raise ValueError("local snapshot payload failed its immutable hash check")
            return payload
        raise ValueError("unsupported snapshot reference")

    def delete(self, reference: str) -> None:
        if not reference.startswith("local://"):
            raise ValueError("unsupported snapshot reference")
        relative = reference.removeprefix("local://")
        provider_id, separator, content_hash = relative.partition("/")
        if not separator or len(content_hash) != 64:
            raise ValueError("invalid local snapshot reference")
        _validate_content_hash(content_hash)
        target = self.root / provider_id / content_hash
        if target.is_symlink() or target.resolve().parent.parent != self.root.resolve():
            raise ValueError("snapshot reference escapes storage root")
        if target.exists():
            target.unlink()


class S3SnapshotStore:
    """S3-compatible immutable snapshot adapter for Cloudflare R2 or equivalent stores."""

    def __init__(self, settings: Settings, *, client: Optional[Any] = None) -> None:
        if not settings.object_storage_bucket:
            raise ValueError("object storage bucket is required")
        if client is None:
            try:
                import boto3  # type: ignore[import-not-found]
            except ImportError as exc:  # pragma: no cover - exercised in deployment packaging
                raise RuntimeError("install the storage extra to use S3 snapshot storage") from exc
            client = boto3.client(
                "s3",
                endpoint_url=settings.object_storage_endpoint_url,
                region_name=settings.object_storage_region,
                aws_access_key_id=settings.object_storage_access_key_id,
                aws_secret_access_key=settings.object_storage_secret_access_key,
            )
        self.client = client
        self.bucket = settings.object_storage_bucket
        self.prefix = settings.object_storage_prefix.strip("/")
        if not self.prefix:
            raise ValueError("object storage prefix is required")

    def _key(self, provider_id: str, content_hash: str) -> str:
        _validate_content_hash(content_hash)
        safe_provider = provider_id.replace("/", "_").replace("..", "_")
        return f"{self.prefix}/{safe_provider}/{content_hash}"

    def _reference_key(self, reference: str) -> tuple[str, str]:
        prefix = f"s3://{self.bucket}/"
        if not reference.startswith(prefix):
            raise ValueError("invalid object-storage reference")
        key = reference.removeprefix(prefix)
        if not key.startswith(f"{self.prefix}/") or ".." in key.split("/"):
            raise ValueError("invalid object-storage key")
        content_hash = key.rsplit("/", 1)[-1]
        _validate_content_hash(content_hash)
        return key, content_hash

    def put(self, provider_id: str, content_hash: str, payload: bytes) -> str:
        key = self._key(provider_id, content_hash)
        reference = f"s3://{self.bucket}/{key}"
        try:
            existing = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception as exc:
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if error_code not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            if hashlib.sha256(existing).hexdigest() != content_hash:
                raise ValueError("immutable object-storage key contains a different payload")
            return reference
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType="application/octet-stream",
            Metadata={"sha256": content_hash, "provider-id": provider_id},
        )
        return reference

    def put_file(self, provider_id: str, content_hash: str, path: Path) -> str:
        key = self._key(provider_id, content_hash)
        reference = f"s3://{self.bucket}/{key}"
        self.client.upload_file(
            str(path),
            self.bucket,
            key,
            ExtraArgs={
                "ContentType": "application/octet-stream",
                "Metadata": {"sha256": content_hash, "provider-id": provider_id},
            },
        )
        return reference

    def read(self, reference: str) -> bytes:
        key, content_hash = self._reference_key(reference)
        payload = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        if hashlib.sha256(payload).hexdigest() != content_hash:
            raise ValueError("object-storage payload failed its immutable hash check")
        return payload

    def delete(self, reference: str) -> None:
        key, _ = self._reference_key(reference)
        self.client.delete_object(Bucket=self.bucket, Key=key)


def build_snapshot_store(settings: Settings) -> SnapshotStore:
    if settings.raw_snapshot_backend == "s3":
        return S3SnapshotStore(settings)
    return LocalSnapshotStore(Path(settings.raw_snapshot_dir))


def _validate_content_hash(content_hash: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        raise ValueError("content hash must be a lowercase SHA-256 hex digest")
