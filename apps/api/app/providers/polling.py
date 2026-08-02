from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.config import Settings
from app.db import SessionLocal
from app.incidents.service import process_retrieval
from app.models import Provider, ProviderHealth, ProviderPollLease, ProviderRetrieval, User
from app.providers.approval import live_polling_decision
from app.providers.ingestion import DispatchIngestionService
from app.providers.registry import (
    ProviderDisabledError,
    SarasotaProviderError,
    build_registry,
)

LOGGER = logging.getLogger(__name__)
SARASOTA_PROVIDER_ID = "sarasota.official_dispatch"
LEASE_SECONDS = 120


@dataclass(frozen=True)
class PollRunResult:
    status: str
    reason: str
    retrieval_id: Optional[str] = None
    processing_run_id: Optional[str] = None
    normalized_record_count: int = 0
    replayed: bool = False
    authorization_basis: Optional[str] = None


class SarasotaPollingService:
    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: Callable = SessionLocal,
        registry=None,
        owner: Optional[str] = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.registry = registry
        self.owner = owner or f"poller:{uuid4()}"

    def poll_once(self) -> PollRunResult:
        request_id = f"sarasota-poll:{uuid4()}"
        with self.session_factory() as db:
            decision = live_polling_decision(db, self.settings)
            if not decision.allowed:
                self._record_skip(db, request_id, decision.reason)
                return PollRunResult("skipped", decision.reason)

            provider = db.get(Provider, SARASOTA_PROVIDER_ID)
            if provider is None:
                reason = "official Sarasota provider is not seeded"
                self._record_skip(db, request_id, reason)
                return PollRunResult(
                    "skipped", reason, authorization_basis=decision.authorization_basis
                )
            if not provider.enabled:
                reason = "official Sarasota provider is disabled by an administrator"
                self._record_skip(db, request_id, reason)
                return PollRunResult(
                    "skipped", reason, authorization_basis=decision.authorization_basis
                )
            if not self._acquire_lease(db):
                return PollRunResult(
                    "skipped",
                    "another Sarasota polling worker holds the lease",
                    authorization_basis=decision.authorization_basis,
                )

            system_user = db.scalar(
                select(User)
                .where(User.is_active.is_(True))
                .order_by(User.created_at, User.id)
                .limit(1)
            )
            if system_user is None:
                return self._fail(
                    db,
                    request_id,
                    "missing_system_user",
                    "Sarasota polling requires an active user for created_by and audit provenance",
                    decision.authorization_basis,
                )

            adapter = (self.registry or build_registry(self.settings)).get(SARASOTA_PROVIDER_ID)
            try:
                snapshot = adapter.retrieve()
                report = DispatchIngestionService(self.settings).ingest(
                    db,
                    provider=provider,
                    user_id=system_user.id,
                    filename="sarasota-dispatch-live.html",
                    content_type=snapshot.content_type,
                    payload=snapshot.payload,
                    idempotency_key=f"live-{_sha256(snapshot.payload)}",
                    authorized_snapshot=False,
                    request_id=request_id,
                    acquisition_mode="live_poll",
                    authorization_basis=decision.authorization_basis,
                )
                run_id = None
                if report.status in {
                    "imported",
                    "imported_with_schema_warning",
                    "replayed_existing_snapshot",
                }:
                    retrieval = db.get(ProviderRetrieval, report.retrieval_id)
                    if retrieval is not None and report.normalized_record_count > 0:
                        run = process_retrieval(
                            db,
                            retrieval,
                            self.settings,
                            actor_user_id=system_user.id,
                            reason="scheduled_live_poll",
                            request_id=request_id,
                        )
                        run_id = run.id
                record_audit(
                    db,
                    action="provider.poll_completed",
                    resource_type="provider_retrieval",
                    resource_id=report.retrieval_id,
                    actor_user_id=system_user.id,
                    request_id=request_id,
                    metadata={
                        "provider_id": SARASOTA_PROVIDER_ID,
                        "status": report.status,
                        "replayed": report.replayed,
                        "normalized_record_count": report.normalized_record_count,
                        "authorization_basis": decision.authorization_basis,
                        "poll_interval_seconds": self.settings.sarasota_poll_interval_seconds,
                    },
                )
                self._finish_lease(db, "completed", None)
                db.commit()
                return PollRunResult(
                    "retrieved" if not report.replayed else "replayed",
                    report.status,
                    retrieval_id=report.retrieval_id,
                    processing_run_id=run_id,
                    normalized_record_count=report.normalized_record_count,
                    replayed=report.replayed,
                    authorization_basis=decision.authorization_basis,
                )
            except ProviderDisabledError as exc:
                db.rollback()
                return self._fail(
                    db, request_id, "provider_disabled", str(exc), decision.authorization_basis
                )
            except SarasotaProviderError as exc:
                db.rollback()
                return self._fail(db, request_id, exc.code, str(exc), decision.authorization_basis)
            except Exception as exc:
                db.rollback()
                LOGGER.exception("Sarasota polling failed")
                return self._fail(
                    db, request_id, "poll_failed", str(exc), decision.authorization_basis
                )

    def _acquire_lease(self, db: Session) -> bool:
        now = datetime.now(timezone.utc)
        lease = db.get(ProviderPollLease, SARASOTA_PROVIDER_ID)
        lease_expires_at = (
            lease.lease_expires_at.replace(tzinfo=timezone.utc)
            if lease is not None and lease.lease_expires_at.tzinfo is None
            else lease.lease_expires_at
            if lease is not None
            else None
        )
        if (
            lease is not None
            and lease_expires_at is not None
            and lease_expires_at > now
            and lease.lease_owner != self.owner
        ):
            db.rollback()
            return False
        if lease is None:
            lease = ProviderPollLease(
                provider_id=SARASOTA_PROVIDER_ID,
                lease_owner=self.owner,
                lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
                last_started_at=now,
            )
            db.add(lease)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return False
            return True
        lease.lease_owner = self.owner
        lease.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        lease.last_started_at = now
        lease.last_error = None
        db.commit()
        return True

    def _finish_lease(self, db: Session, status: str, error: Optional[str]) -> None:
        lease = db.get(ProviderPollLease, SARASOTA_PROVIDER_ID)
        if lease is not None:
            lease.last_finished_at = datetime.now(timezone.utc)
            lease.last_status = status
            lease.last_error = error
            lease.lease_expires_at = datetime.now(timezone.utc)

    def _record_skip(self, db: Session, request_id: str, reason: str) -> None:
        record_audit(
            db,
            action="provider.poll_skipped",
            resource_type="provider",
            resource_id=SARASOTA_PROVIDER_ID,
            actor_user_id=None,
            request_id=request_id,
            metadata={
                "reason": reason,
                "poll_interval_seconds": self.settings.sarasota_poll_interval_seconds,
            },
        )
        db.commit()

    def _fail(
        self,
        db: Session,
        request_id: str,
        code: str,
        message: str,
        authorization_basis: Optional[str],
    ) -> PollRunResult:
        health = db.scalar(
            select(ProviderHealth).where(ProviderHealth.provider_id == SARASOTA_PROVIDER_ID)
        )
        if health is not None:
            health.failure_count = (health.failure_count or 0) + 1
            health.last_retrieval_status = "poll_failed"
            health.circuit_state = "open" if health.failure_count >= 3 else "closed"
            health.known_status_note = message
        self._finish_lease(db, "failed", message)
        record_audit(
            db,
            action="provider.poll_failed",
            resource_type="provider",
            resource_id=SARASOTA_PROVIDER_ID,
            actor_user_id=None,
            request_id=request_id,
            metadata={
                "error_code": code,
                "error": message,
                "authorization_basis": authorization_basis,
                "poll_interval_seconds": self.settings.sarasota_poll_interval_seconds,
            },
        )
        db.commit()
        return PollRunResult("failed", message, authorization_basis=authorization_basis)


class SarasotaPollingWorker:
    def __init__(self, service: SarasotaPollingService) -> None:
        self.service = service

    async def run(self) -> None:
        while True:
            result = await asyncio.to_thread(self.service.poll_once)
            LOGGER.info(
                "Sarasota polling cycle finished status=%s reason=%s retrieval_id=%s",
                result.status,
                result.reason,
                result.retrieval_id,
            )
            await asyncio.sleep(self.service.settings.sarasota_poll_interval_seconds)


def _sha256(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()
