from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.config import Settings
from app.models import (
    DispatchObservation,
    ImportErrorRecord,
    ImportJob,
    ParserVersion,
    Provider,
    ProviderHealth,
    ProviderRetrieval,
    RawDispatchRow,
    RawSnapshot,
    SchemaAlert,
)
from app.providers.parsing import (
    EXPECTED_FIELDS,
    PARSER_VERSION,
    REQUIRED_FIELDS,
    SCHEMA_VERSION,
    ParseIssue,
    ParseResult,
    parse_snapshot,
)
from app.providers.storage import LocalSnapshotStore, SnapshotStore

MAX_FAILURES_BEFORE_CIRCUIT_OPEN = 3


class IdempotencyConflict(ValueError):
    pass


class SnapshotTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class IngestionReport:
    import_job_id: str
    retrieval_id: str
    provider_id: str
    status: str
    format: str
    parser_version: str
    schema_version: str
    content_hash: str
    normalized_record_count: int
    rejected_record_count: int
    schema_alert_count: int
    replayed: bool
    error: Optional[str]
    acquisition_mode: str
    authorization_basis: Optional[str]
    created_at: datetime


def report_from_job(db: Session, job: ImportJob, replayed: bool) -> IngestionReport:
    retrieval = db.get(ProviderRetrieval, job.retrieval_id) if job.retrieval_id else None
    if retrieval is None:
        return IngestionReport(
            import_job_id=job.id,
            retrieval_id="",
            provider_id=job.provider_id,
            status=job.status,
            format="unknown",
            parser_version="unknown",
            schema_version="unknown",
            content_hash=job.request_hash,
            normalized_record_count=0,
            rejected_record_count=0,
            schema_alert_count=0,
            replayed=replayed,
            error="legacy import job has no retrieval reference",
            acquisition_mode="unknown",
            authorization_basis=None,
            created_at=job.created_at,
        )
    alert_count = db.scalar(
        select(func.count())
        .select_from(SchemaAlert)
        .where(SchemaAlert.retrieval_id == retrieval.id)
    )
    return IngestionReport(
        import_job_id=job.id,
        retrieval_id=retrieval.id,
        provider_id=job.provider_id,
        status=job.status,
        format=_format_from_content_type(
            db.scalar(
                select(RawSnapshot.content_type).where(RawSnapshot.retrieval_id == retrieval.id)
            )
            or "unknown"
        ),
        parser_version=retrieval.parser_version,
        schema_version=retrieval.schema_version,
        content_hash=retrieval.snapshot_hash or job.request_hash,
        normalized_record_count=retrieval.normalized_record_count,
        rejected_record_count=retrieval.rejected_record_count,
        schema_alert_count=alert_count or 0,
        replayed=replayed,
        error=retrieval.error_message,
        acquisition_mode=retrieval.acquisition_mode,
        authorization_basis=retrieval.authorization_basis,
        created_at=job.created_at,
    )


def _format_from_content_type(content_type: str) -> str:
    content_type = content_type.lower()
    if "html" in content_type:
        return "html"
    if "csv" in content_type:
        return "csv"
    if "json" in content_type:
        return "json"
    return "unknown"


def _job_idempotency_key(provider_id: str, key: str) -> str:
    return f"{provider_id}:{key}"


def _parser_version_id(provider_id: str, version: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"beyond-fire-radar:parser:{provider_id}:{version}"))


def seed_parser_versions(db: Session) -> None:
    expected = list(EXPECTED_FIELDS)
    required = list(REQUIRED_FIELDS)
    for provider_id in ("sarasota.official_dispatch", "fixture.sarasota.dispatch"):
        existing = db.scalar(
            select(ParserVersion).where(
                ParserVersion.provider_id == provider_id,
                ParserVersion.version == PARSER_VERSION,
            )
        )
        if existing is None:
            db.add(
                ParserVersion(
                    id=_parser_version_id(provider_id, PARSER_VERSION),
                    provider_id=provider_id,
                    version=PARSER_VERSION,
                    format="csv/html/json",
                    expected_fields=expected,
                    required_fields=required,
                    active=True,
                )
            )
    db.commit()


class DispatchIngestionService:
    def __init__(self, settings: Settings, store: Optional[SnapshotStore] = None) -> None:
        self.settings = settings
        self.store = store or LocalSnapshotStore(Path(settings.raw_snapshot_dir))

    def ingest(
        self,
        db: Session,
        *,
        provider: Provider,
        user_id: str,
        filename: str,
        content_type: Optional[str],
        payload: bytes,
        idempotency_key: str,
        authorized_snapshot: bool,
        request_id: str,
    ) -> IngestionReport:
        if len(payload) > self.settings.max_snapshot_bytes:
            raise SnapshotTooLarge(
                f"snapshot exceeds the configured {self.settings.max_snapshot_bytes} byte limit"
            )
        if provider.id == "sarasota.official_dispatch" and not authorized_snapshot:
            raise PermissionError(
                "manual Sarasota snapshots require an explicit authorized_snapshot attestation"
            )

        content_hash = hashlib.sha256(payload).hexdigest()
        request_hash = content_hash
        scoped_key = _job_idempotency_key(provider.id, idempotency_key)
        existing_job = db.scalar(select(ImportJob).where(ImportJob.idempotency_key == scoped_key))
        if existing_job is not None:
            if existing_job.request_hash != request_hash:
                raise IdempotencyConflict(
                    "Idempotency-Key was already used for a different snapshot"
                ) from None
            return report_from_job(db, existing_job, replayed=True)

        # Reserve the idempotency key in the same transaction as the retrieval. A concurrent
        # request blocks on the unique constraint and then returns this completed job instead of
        # creating a second retrieval or leaking an IntegrityError to the API client.
        job = ImportJob(
            id=str(uuid4()),
            provider_id=provider.id,
            status="parsing",
            source_filename=filename,
            idempotency_key=scoped_key,
            request_hash=request_hash,
            retrieval_id=None,
            created_by=user_id,
        )
        db.add(job)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing_job = db.scalar(
                select(ImportJob).where(ImportJob.idempotency_key == scoped_key)
            )
            if existing_job is None:
                raise
            if existing_job.request_hash != request_hash:
                raise IdempotencyConflict(
                    "Idempotency-Key was already used for a different snapshot"
                ) from None
            return report_from_job(db, existing_job, replayed=True)

        existing_snapshot = db.scalar(
            select(RawSnapshot).where(
                RawSnapshot.provider_id == provider.id,
                RawSnapshot.content_hash == content_hash,
            )
        )
        if existing_snapshot is not None:
            retrieval = db.get(ProviderRetrieval, existing_snapshot.retrieval_id)
            if retrieval is None:
                raise RuntimeError("raw snapshot points to a missing retrieval")
            job.status = "replayed_existing_snapshot"
            job.retrieval_id = retrieval.id
            record_audit(
                db,
                action="provider.snapshot_replayed",
                resource_type="provider_retrieval",
                resource_id=retrieval.id,
                actor_user_id=user_id,
                request_id=request_id,
                metadata={"provider_id": provider.id, "content_hash": content_hash},
            )
            db.commit()
            return report_from_job(db, job, replayed=True)

        raw_reference = self.store.put(provider.id, content_hash, payload)
        retrieved_at = datetime.now(timezone.utc)
        retrieval = ProviderRetrieval(
            id=str(uuid4()),
            provider_id=provider.id,
            status="parsing",
            retrieved_at=retrieved_at,
            snapshot_hash=content_hash,
            schema_version=SCHEMA_VERSION,
            parser_version=PARSER_VERSION,
            circuit_state="closed",
            acquisition_mode=(
                "synthetic_fixture"
                if provider.id == "fixture.sarasota.dispatch"
                else "manual_snapshot"
            ),
            authorization_basis=(
                "fixture" if provider.id == "fixture.sarasota.dispatch" else "manual_attestation"
            ),
        )
        db.add(retrieval)
        db.flush()
        raw_snapshot = RawSnapshot(
            id=str(uuid4()),
            provider_id=provider.id,
            retrieval_id=retrieval.id,
            content_hash=content_hash,
            content_type=content_type or "application/octet-stream",
            payload_reference=raw_reference,
            byte_size=len(payload),
        )
        db.add(raw_snapshot)
        job.retrieval_id = retrieval.id
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing_snapshot = db.scalar(
                select(RawSnapshot).where(RawSnapshot.content_hash == content_hash)
            )
            if existing_snapshot is None:
                raise
            if existing_snapshot.provider_id != provider.id:
                raise ValueError(
                    "snapshot hash is already associated with a different provider"
                ) from None
            existing_retrieval = db.get(ProviderRetrieval, existing_snapshot.retrieval_id)
            if existing_retrieval is None:
                raise RuntimeError("raw snapshot points to a missing retrieval") from None
            replay_job = ImportJob(
                id=str(uuid4()),
                provider_id=provider.id,
                status="replayed_existing_snapshot",
                source_filename=filename,
                idempotency_key=scoped_key,
                request_hash=request_hash,
                retrieval_id=existing_retrieval.id,
                created_by=user_id,
            )
            db.add(replay_job)
            record_audit(
                db,
                action="provider.snapshot_replayed",
                resource_type="provider_retrieval",
                resource_id=existing_retrieval.id,
                actor_user_id=user_id,
                request_id=request_id,
                metadata={"provider_id": provider.id, "content_hash": content_hash},
            )
            db.commit()
            return report_from_job(db, replay_job, replayed=True)

        try:
            parsed = parse_snapshot(payload, content_type, filename)
        except Exception as exc:
            parsed = ParseResult(
                format="unknown",
                parser_version=PARSER_VERSION,
                schema_version=SCHEMA_VERSION,
                issues=[],
            )
            parsed.issues.append(ParseIssue("parse_failed", str(exc)))

        self._persist_parse_result(
            db,
            provider=provider,
            retrieval=retrieval,
            job=job,
            raw_snapshot=raw_snapshot,
            parsed=parsed,
            retrieved_at=retrieved_at,
            raw_reference=raw_reference,
        )
        self._update_health(db, provider.id, retrieval, parsed)
        record_audit(
            db,
            action="provider.snapshot_imported",
            resource_type="provider_retrieval",
            resource_id=retrieval.id,
            actor_user_id=user_id,
            request_id=request_id,
            metadata={
                "provider_id": provider.id,
                "status": retrieval.status,
                "content_hash": content_hash,
                "normalized_record_count": retrieval.normalized_record_count,
                "rejected_record_count": retrieval.rejected_record_count,
                "schema_alert_count": len(
                    [
                        issue
                        for issue in parsed.issues
                        if issue.code in {"schema_drift", "schema_warning", "zero_row_anomaly"}
                    ]
                ),
                "authorized_snapshot_attestation": authorized_snapshot,
            },
        )
        db.commit()
        return report_from_job(db, job, replayed=False)

    def compare(
        self, db: Session, retrieval: ProviderRetrieval, parser_version: str
    ) -> ParseResult:
        if parser_version != PARSER_VERSION:
            raise ValueError(f"parser version {parser_version} is not registered")
        raw_snapshot = db.scalar(
            select(RawSnapshot).where(RawSnapshot.retrieval_id == retrieval.id)
        )
        if raw_snapshot is None:
            raise ValueError("retrieval has no raw snapshot")
        return parse_snapshot(
            self.store.read(raw_snapshot.payload_reference),
            raw_snapshot.content_type,
            "comparison.snapshot",
            parser_version=parser_version,
        )

    def _persist_parse_result(
        self,
        db: Session,
        *,
        provider: Provider,
        retrieval: ProviderRetrieval,
        job: ImportJob,
        raw_snapshot: RawSnapshot,
        parsed: ParseResult,
        retrieved_at: datetime,
        raw_reference: str,
    ) -> None:
        retrieval.parser_version = parsed.parser_version
        retrieval.schema_version = parsed.schema_version
        retrieval.normalized_record_count = len(parsed.rows)
        retrieval.rejected_record_count = sum(
            1 for issue in parsed.issues if issue.row_number is not None
        )
        if parsed.issues and any(
            issue.code in {"parse_failed", "schema_drift", "unsupported_format"}
            for issue in parsed.issues
        ):
            retrieval.status = "parse_failed"
            retrieval.error_code = next(
                issue.code
                for issue in parsed.issues
                if issue.code in {"parse_failed", "schema_drift", "unsupported_format"}
            )
            retrieval.error_message = next(
                issue.message
                for issue in parsed.issues
                if issue.code in {"parse_failed", "schema_drift", "unsupported_format"}
            )
        elif not parsed.rows:
            retrieval.status = "zero_row_anomaly"
            retrieval.error_code = "zero_row_anomaly"
            retrieval.error_message = "parser produced zero rows; prior data was retained"
        elif any(issue.code == "schema_warning" for issue in parsed.issues):
            retrieval.status = "imported_with_schema_warning"
        else:
            retrieval.status = "imported"
        job.status = retrieval.status

        for issue in parsed.issues:
            db.add(
                ImportErrorRecord(
                    id=str(uuid4()),
                    import_job_id=job.id,
                    row_number=issue.row_number,
                    code=issue.code,
                    message=issue.message,
                    raw_payload=issue.raw_payload,
                )
            )
        if parsed.schema and parsed.schema.code:
            db.add(
                SchemaAlert(
                    id=str(uuid4()),
                    provider_id=provider.id,
                    retrieval_id=retrieval.id,
                    parser_version=parsed.parser_version,
                    severity=parsed.schema.severity,
                    code=parsed.schema.code,
                    observed_fields=parsed.schema.observed_fields,
                    missing_required_fields=parsed.schema.missing_required_fields,
                    unexpected_fields=parsed.schema.unexpected_fields,
                    message=parsed.schema.message or "schema changed",
                )
            )
        elif any(issue.code == "zero_row_anomaly" for issue in parsed.issues):
            observed_fields = parsed.schema.observed_fields if parsed.schema else []
            db.add(
                SchemaAlert(
                    id=str(uuid4()),
                    provider_id=provider.id,
                    retrieval_id=retrieval.id,
                    parser_version=parsed.parser_version,
                    severity="error",
                    code="zero_row_anomaly",
                    observed_fields=observed_fields,
                    missing_required_fields=[],
                    unexpected_fields=[],
                    message="snapshot parsed successfully but contained zero data rows",
                )
            )

        for row in parsed.rows:
            row_hash = hashlib.sha256(
                json.dumps(row.raw_payload, ensure_ascii=False, sort_keys=True, default=str).encode(
                    "utf-8"
                )
            ).hexdigest()
            raw_row = RawDispatchRow(
                id=str(uuid4()),
                raw_snapshot_id=raw_snapshot.id,
                provider_id=provider.id,
                row_number=row.row_number,
                source_record_id=row.source_record_id,
                row_hash=row_hash,
                raw_payload=json.dumps(
                    row.raw_payload, ensure_ascii=False, sort_keys=True, default=str
                ),
            )
            db.add(raw_row)
            db.flush()
            db.add(
                DispatchObservation(
                    id=str(uuid4()),
                    raw_dispatch_row_id=raw_row.id,
                    raw_snapshot_id=raw_snapshot.id,
                    provider_id=provider.id,
                    source_record_id=row.source_record_id,
                    source_event_id=row.source_event_id,
                    source_case_number=row.source_case_number,
                    agency=row.agency,
                    station=row.station,
                    event_time=row.event_time,
                    retrieved_at=retrieved_at,
                    original_event_type=row.original_event_type,
                    normalized_event_family=row.normalized_event_family,
                    original_location=row.original_location,
                    location_precision=row.location_precision,
                    latitude=row.latitude,
                    longitude=row.longitude,
                    grid=row.grid,
                    parser_confidence=row.parser_confidence,
                    parser_version=parsed.parser_version,
                    taxonomy_version="event-taxonomy.v1",
                    raw_payload_reference=raw_reference,
                )
            )

    @staticmethod
    def _update_health(
        db: Session, provider_id: str, retrieval: ProviderRetrieval, parsed: ParseResult
    ) -> None:
        health = db.scalar(select(ProviderHealth).where(ProviderHealth.provider_id == provider_id))
        if health is None:
            health = ProviderHealth(
                id=str(uuid4()), provider_id=provider_id, known_status_note="created during import"
            )
            db.add(health)
        health.last_retrieval_status = retrieval.status
        has_schema_alert = bool(parsed.schema and parsed.schema.code) or any(
            issue.code == "zero_row_anomaly" for issue in parsed.issues
        )
        health.schema_drift_detected = has_schema_alert
        health.schema_alert_count = (health.schema_alert_count or 0) + (
            1 if has_schema_alert else 0
        )
        if (
            retrieval.status in {"imported", "imported_with_schema_warning"}
            and retrieval.normalized_record_count > 0
        ):
            health.last_successful_retrieval = retrieval.retrieved_at
            if health.last_snapshot_hash != retrieval.snapshot_hash:
                health.last_changed_retrieval = retrieval.retrieved_at
            health.last_snapshot_hash = retrieval.snapshot_hash
            health.failure_count = 0
            health.circuit_state = "closed"
            health.known_status_note = "Last retrieval parsed with preserved raw rows."
        else:
            health.failure_count = (health.failure_count or 0) + 1
            health.circuit_state = (
                "open" if health.failure_count >= MAX_FAILURES_BEFORE_CIRCUIT_OPEN else "closed"
            )
            health.known_status_note = (
                retrieval.error_message or "Retrieval did not produce usable rows."
            )
