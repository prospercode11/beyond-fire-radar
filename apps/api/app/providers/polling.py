from __future__ import annotations

import asyncio
import logging
import threading
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
from app.incidents.service import process_retrieval, unprocessed_retrievals
from app.models import (
    Provider,
    ProviderHealth,
    ProviderPollLease,
    ProviderRetrieval,
    User,
)
from app.opportunities.scoring import ensure_fire_score_runs
from app.providers.approval import live_polling_decision
from app.providers.ingestion import DispatchIngestionService
from app.providers.registry import (
    BrowardProviderError,
    MiamiDadeProviderError,
    ProviderDisabledError,
    SarasotaProviderError,
    build_registry,
)

LOGGER = logging.getLogger(__name__)
POLLING_RUN_LOCK = threading.Lock()
SARASOTA_PROVIDER_ID = "sarasota.official_dispatch"
MIAMI_DADE_PROVIDER_ID = "miami_dade.fire_calls"
BROWARD_PROVIDER_ID = "broward.efirstalert_dispatch"
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
    recovered_retrieval_count: int = 0
    recovered_observation_count: int = 0


@dataclass(frozen=True)
class ProcessingRecoveryResult:
    pending_retrieval_count: int
    pending_observation_count: int
    recovered_retrieval_ids: tuple[str, ...] = ()

    @property
    def recovered_retrieval_count(self) -> int:
        return len(self.recovered_retrieval_ids)


class SarasotaPollingService:
    provider_id = SARASOTA_PROVIDER_ID
    provider_label = "Sarasota"
    request_prefix = "sarasota-poll"

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
        with POLLING_RUN_LOCK:
            return self._poll_once()

    def _poll_once(self) -> PollRunResult:
        request_id = f"{self.request_prefix}:{uuid4()}"
        with self.session_factory() as db:
            decision = live_polling_decision(db, self.settings, self.provider_id)
            if not decision.allowed:
                self._record_skip(db, request_id, decision.reason)
                return PollRunResult("skipped", decision.reason)

            provider = db.get(Provider, self.provider_id)
            if provider is None:
                reason = f"official {self.provider_label} provider is not seeded"
                self._record_skip(db, request_id, reason)
                return PollRunResult(
                    "skipped", reason, authorization_basis=decision.authorization_basis
                )
            if not provider.enabled:
                reason = f"official {self.provider_label} provider is disabled by an administrator"
                self._record_skip(db, request_id, reason)
                return PollRunResult(
                    "skipped", reason, authorization_basis=decision.authorization_basis
                )
            if not self._acquire_lease(db):
                return PollRunResult(
                    "skipped",
                    f"another {self.provider_label} polling worker holds the lease",
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
                    f"{self.provider_label} polling requires an active user for created_by and audit provenance",
                    decision.authorization_basis,
                )

            adapter = (self.registry or build_registry(self.settings)).get(self.provider_id)
            try:
                recovery = self._recover_unprocessed_retrievals(
                    db,
                    actor_user_id=system_user.id,
                    request_id=request_id,
                )
                snapshot = adapter.retrieve()
                report = DispatchIngestionService(self.settings).ingest(
                    db,
                    provider=provider,
                    user_id=system_user.id,
                    filename=f"{self.provider_id}-live.html",
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
                        self._score_new_fire_opportunities(db, system_user.id)
                health = db.scalar(
                    select(ProviderHealth).where(ProviderHealth.provider_id == self.provider_id)
                )
                if health is not None and report.status in {
                    "imported",
                    "imported_with_schema_warning",
                    "replayed_existing_snapshot",
                }:
                    health.failure_count = 0
                    health.circuit_state = "closed"
                    health.last_retrieval_status = "imported"
                    health.known_status_note = (
                        "Last polling cycle completed with preserved raw rows."
                        if not recovery.recovered_retrieval_count
                        else (
                            "Last polling cycle completed with preserved raw rows and "
                            f"recovered {recovery.recovered_retrieval_count} retained "
                            "retrieval(s) that had not reached incident processing."
                        )
                    )
                record_audit(
                    db,
                    action="provider.poll_completed",
                    resource_type="provider_retrieval",
                    resource_id=report.retrieval_id,
                    actor_user_id=system_user.id,
                    request_id=request_id,
                    metadata={
                        "provider_id": self.provider_id,
                        "status": report.status,
                        "replayed": report.replayed,
                        "normalized_record_count": report.normalized_record_count,
                        "authorization_basis": decision.authorization_basis,
                        "poll_interval_seconds": self.poll_interval_seconds,
                        "recovered_retrieval_count": recovery.recovered_retrieval_count,
                        "recovered_observation_count": recovery.pending_observation_count,
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
                    recovered_retrieval_count=recovery.recovered_retrieval_count,
                    recovered_observation_count=recovery.pending_observation_count,
                )
            except ProviderDisabledError as exc:
                db.rollback()
                return self._fail(
                    db, request_id, "provider_disabled", str(exc), decision.authorization_basis
                )
            except (SarasotaProviderError, MiamiDadeProviderError, BrowardProviderError) as exc:
                db.rollback()
                return self._fail(db, request_id, exc.code, str(exc), decision.authorization_basis)
            except Exception as exc:
                db.rollback()
                LOGGER.exception("Sarasota polling failed")
                return self._fail(
                    db, request_id, "poll_failed", str(exc), decision.authorization_basis
                )

    def _recover_unprocessed_retrievals(
        self,
        db: Session,
        *,
        actor_user_id: str,
        request_id: str,
    ) -> ProcessingRecoveryResult:
        """Finish retained live snapshots before collecting another one.

        Ingestion persists raw source bytes in an independent commit. If later incident
        assembly fails, this loop makes the next approved poll recover those rows rather
        than letting a newer successful retrieval hide the failure.
        """

        pending = unprocessed_retrievals(db, provider_id=self.provider_id)
        pending_observation_count = sum(item.normalized_record_count for item in pending)
        recovered_ids: list[str] = []
        for retrieval in pending:
            run = process_retrieval(
                db,
                retrieval,
                self.settings,
                actor_user_id=actor_user_id,
                reason="scheduled_live_poll_recovery",
                request_id=f"{request_id}:recover:{retrieval.id}",
            )
            self._score_new_fire_opportunities(db, actor_user_id)
            record_audit(
                db,
                action="provider.retrieval_recovered",
                resource_type="provider_retrieval",
                resource_id=retrieval.id,
                actor_user_id=actor_user_id,
                request_id=f"{request_id}:recover:{retrieval.id}",
                metadata={
                    "provider_id": self.provider_id,
                    "processing_run_id": run.id,
                    "normalized_record_count": retrieval.normalized_record_count,
                    "reason": "retained_snapshot_processing_recovery",
                },
            )
            # Preserve each recovered snapshot even if a later queued retrieval fails.
            db.commit()
            recovered_ids.append(retrieval.id)
        return ProcessingRecoveryResult(
            pending_retrieval_count=len(pending),
            pending_observation_count=pending_observation_count,
            recovered_retrieval_ids=tuple(recovered_ids),
        )

    def recover_unprocessed_retrievals(self, *, dry_run: bool = False) -> ProcessingRecoveryResult:
        """Operator-safe recovery entry point used by the audited repair command."""

        with POLLING_RUN_LOCK:
            with self.session_factory() as db:
                pending = unprocessed_retrievals(db, provider_id=self.provider_id)
                if dry_run:
                    return ProcessingRecoveryResult(
                        pending_retrieval_count=len(pending),
                        pending_observation_count=sum(
                            item.normalized_record_count for item in pending
                        ),
                    )
                if not pending:
                    return ProcessingRecoveryResult(
                        pending_retrieval_count=0,
                        pending_observation_count=0,
                    )
                decision = live_polling_decision(db, self.settings, self.provider_id)
                if not decision.allowed:
                    raise PermissionError(decision.reason)
                provider = db.get(Provider, self.provider_id)
                if provider is None or not provider.enabled:
                    raise RuntimeError(
                        f"{self.provider_label} provider is unavailable for recovery"
                    )
                if not self._acquire_lease(db):
                    raise RuntimeError(
                        f"another {self.provider_label} polling worker holds the lease"
                    )
                system_user = db.scalar(
                    select(User)
                    .where(User.is_active.is_(True))
                    .order_by(User.created_at, User.id)
                    .limit(1)
                )
                if system_user is None:
                    raise RuntimeError("an active user is required for recovery provenance")
                request_id = f"{self.request_prefix}:recovery:{uuid4()}"
                try:
                    result = self._recover_unprocessed_retrievals(
                        db,
                        actor_user_id=system_user.id,
                        request_id=request_id,
                    )
                    health = db.scalar(
                        select(ProviderHealth).where(ProviderHealth.provider_id == self.provider_id)
                    )
                    if health is not None:
                        health.known_status_note = (
                            "No retained retrievals required processing recovery."
                            if not result.recovered_retrieval_count
                            else (
                                f"Recovered {result.recovered_retrieval_count} retained "
                                "retrieval(s) into canonical incidents."
                            )
                        )
                    self._finish_lease(db, "completed", None)
                    db.commit()
                    return result
                except Exception as exc:
                    db.rollback()
                    self._fail(
                        db,
                        request_id,
                        "processing_recovery_failed",
                        str(exc),
                        decision.authorization_basis,
                    )
                    raise

    def _acquire_lease(self, db: Session) -> bool:
        now = datetime.now(timezone.utc)
        lease = db.get(ProviderPollLease, self.provider_id)
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
                provider_id=self.provider_id,
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
        lease = db.get(ProviderPollLease, self.provider_id)
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
            resource_id=self.provider_id,
            actor_user_id=None,
            request_id=request_id,
            metadata={
                "reason": reason,
                "poll_interval_seconds": self.poll_interval_seconds,
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
            select(ProviderHealth).where(ProviderHealth.provider_id == self.provider_id)
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
            resource_id=self.provider_id,
            actor_user_id=None,
            request_id=request_id,
            metadata={
                "error_code": code,
                "error": message,
                "authorization_basis": authorization_basis,
                "poll_interval_seconds": self.poll_interval_seconds,
            },
        )
        db.commit()
        return PollRunResult("failed", message, authorization_basis=authorization_basis)

    @property
    def poll_interval_seconds(self) -> int:
        return (
            self.settings.miami_dade_poll_interval_seconds
            if self.provider_id == MIAMI_DADE_PROVIDER_ID
            else self.settings.broward_poll_interval_seconds
            if self.provider_id == BROWARD_PROVIDER_ID
            else self.settings.sarasota_poll_interval_seconds
        )

    def _score_new_fire_opportunities(self, db: Session, actor_user_id: str) -> None:
        ensure_fire_score_runs(
            db,
            actor_user_id=actor_user_id,
            provider_id=self.provider_id,
        )

    def backfill_scores(self) -> None:
        """Backfill score runs before the first scheduled 15-minute poll."""

        with POLLING_RUN_LOCK:
            with self.session_factory() as db:
                system_user = db.scalar(
                    select(User)
                    .where(User.is_active.is_(True))
                    .order_by(User.created_at, User.id)
                    .limit(1)
                )
                if system_user is None:
                    return
                self._score_new_fire_opportunities(db, system_user.id)
                db.commit()


class MiamiDadePollingService(SarasotaPollingService):
    provider_id = MIAMI_DADE_PROVIDER_ID
    provider_label = "Miami-Dade"
    request_prefix = "miami-dade-poll"


class BrowardPollingService(SarasotaPollingService):
    provider_id = BROWARD_PROVIDER_ID
    provider_label = "Broward eFirstAlert"
    request_prefix = "broward-poll"


class SarasotaPollingWorker:
    def __init__(self, service: SarasotaPollingService) -> None:
        self.service = service

    async def run(self) -> None:
        try:
            await asyncio.to_thread(self.service.backfill_scores)
        except Exception:
            LOGGER.exception(
                "%s score backfill failed; scheduled polling will continue",
                self.service.provider_label,
            )
        loop = asyncio.get_running_loop()
        next_started_at = loop.time()
        while True:
            result = await asyncio.to_thread(self.service.poll_once)
            LOGGER.info(
                "Sarasota polling cycle finished status=%s reason=%s retrieval_id=%s",
                result.status,
                result.reason,
                result.retrieval_id,
            )
            # Schedule from the previous cycle start, not completion. A normal fetch and
            # parse must not silently extend the advertised 15-minute cadence.
            next_started_at += self.service.poll_interval_seconds
            await asyncio.sleep(max(0.0, next_started_at - loop.time()))


class MiamiDadePollingWorker(SarasotaPollingWorker):
    pass


class BrowardPollingWorker(SarasotaPollingWorker):
    pass


def _sha256(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()
