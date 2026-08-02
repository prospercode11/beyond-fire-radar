#!/usr/bin/env python3
"""Apply the documented raw-payload retention policy with a dry-run safety default."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.audit import record_audit
from app.config import get_settings
from app.db import SessionLocal
from app.models import PropertyImport, RawSnapshot
from app.providers.storage import build_snapshot_store
from sqlalchemy import or_, select

RetentionRecord = Any


def _record_kind(model: RetentionRecord) -> tuple[str, str]:
    if model is RawSnapshot:
        return "raw_snapshot", "raw"
    return "property_import", "property"


def _payload_reference(model: RetentionRecord, record: Any) -> str:
    return record.payload_reference if model is RawSnapshot else record.raw_payload_reference


def _candidates(model: RetentionRecord, cutoff: datetime) -> list[str]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(model.id)
                .where(
                    model.payload_purged_at.is_(None),
                    or_(
                        model.payload_purge_pending_at.is_not(None),
                        model.created_at < cutoff,
                    ),
                )
                .order_by(model.created_at, model.id)
            ).all()
        )


def _start_purge(model: RetentionRecord, record_id: str, *, request_id: str, days: int) -> str:
    resource_type, label = _record_kind(model)
    with SessionLocal() as db:
        record = db.get(model, record_id)
        if record is None:
            raise LookupError(f"retention record not found: {resource_type}/{record_id}")
        if record.payload_purged_at is not None:
            return _payload_reference(model, record)
        record.payload_purge_pending_at = record.payload_purge_pending_at or datetime.now(
            timezone.utc
        )
        record_audit(
            db,
            action=f"retention.{label}_payload_purge_started",
            resource_type=resource_type,
            resource_id=record.id,
            actor_user_id=None,
            request_id=request_id,
            metadata={
                "content_hash": record.content_hash,
                "retention_days": days,
                "payload_reference": _payload_reference(model, record),
            },
        )
        db.commit()
        return _payload_reference(model, record)


def _finish_purge(
    model: RetentionRecord,
    record_id: str,
    *,
    request_id: str,
    deletion_status: str,
) -> None:
    resource_type, label = _record_kind(model)
    with SessionLocal() as db:
        record = db.get(model, record_id)
        if record is None or record.payload_purged_at is not None:
            return
        record.payload_purged_at = datetime.now(timezone.utc)
        record.payload_purge_pending_at = None
        record_audit(
            db,
            action=f"retention.{label}_payload_purged",
            resource_type=resource_type,
            resource_id=record.id,
            actor_user_id=None,
            request_id=request_id,
            metadata={
                "content_hash": record.content_hash,
                "payload_reference": _payload_reference(model, record),
                "deletion_status": deletion_status,
            },
        )
        db.commit()


def _fail_purge(
    model: RetentionRecord, record_id: str, *, request_id: str, error: Exception
) -> None:
    resource_type, label = _record_kind(model)
    with SessionLocal() as db:
        record = db.get(model, record_id)
        if record is None:
            return
        # Keep the pending marker. A later run can retry the deletion or reconcile a payload
        # that was deleted immediately before a worker/process failure.
        record_audit(
            db,
            action=f"retention.{label}_payload_purge_failed",
            resource_type=resource_type,
            resource_id=record.id,
            actor_user_id=None,
            request_id=request_id,
            metadata={
                "content_hash": record.content_hash,
                "payload_reference": _payload_reference(model, record),
                "error_type": type(error).__name__,
            },
        )
        db.commit()


def _purge_record(
    model: RetentionRecord, record_id: str, *, store: Any, request_id: str, days: int
) -> str:
    reference = _start_purge(model, record_id, request_id=request_id, days=days)
    try:
        store.delete(reference)
    except FileNotFoundError:
        _finish_purge(model, record_id, request_id=request_id, deletion_status="already_missing")
        return "missing"
    except Exception as error:  # noqa: BLE001 - failure is recorded and the item stays pending
        _fail_purge(model, record_id, request_id=request_id, error=error)
        return "failed"
    _finish_purge(model, record_id, request_id=request_id, deletion_status="deleted")
    return "purged"


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=settings.raw_snapshot_retention_days)
    parser.add_argument(
        "--apply", action="store_true", help="purge payload bytes; default is dry-run"
    )
    parser.add_argument("--confirm", action="store_true", help="required with --apply")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be positive")
    if args.apply and not args.confirm:
        parser.error("--apply requires --confirm because payload deletion is irreversible")

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    request_id = f"retention-{uuid4()}"
    records: list[tuple[Any, str]] = [
        (RawSnapshot, record_id) for record_id in _candidates(RawSnapshot, cutoff)
    ]
    records.extend((PropertyImport, record_id) for record_id in _candidates(PropertyImport, cutoff))
    purged_count = 0
    missing_payload_count = 0
    failed_count = 0
    result: dict[str, object] = {
        "cutoff": cutoff.isoformat(),
        "dry_run": not args.apply,
        "candidate_count": len(records),
        "purged_count": purged_count,
        "missing_payload_count": missing_payload_count,
        "failed_count": failed_count,
        "property_candidate_count": sum(model is PropertyImport for model, _ in records),
    }
    if args.apply:
        store = build_snapshot_store(settings)
        for model, record_id in records:
            outcome = _purge_record(
                model, record_id, store=store, request_id=request_id, days=args.days
            )
            if outcome in {"purged", "missing"}:
                purged_count += 1
            if outcome == "missing":
                missing_payload_count += 1
            if outcome == "failed":
                failed_count += 1
        result["purged_count"] = purged_count
        result["missing_payload_count"] = missing_payload_count
        result["failed_count"] = failed_count
    print(result)


if __name__ == "__main__":
    main()
