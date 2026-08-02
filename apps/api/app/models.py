from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JsonType = JSON


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    roles: Mapped[list[Role]] = relationship(secondary="user_roles", back_populates="users")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    users: Mapped[list[User]] = relationship(secondary="user_roles", back_populates="roles")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class SessionToken(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_authority: Mapped[str] = mapped_column(String(200), nullable=False)
    geographic_coverage: Mapped[str] = mapped_column(String(200), nullable=False)
    data_type: Mapped[str] = mapped_column(String(100), nullable=False)
    authentication_method: Mapped[str] = mapped_column(String(100), nullable=False)
    authorized_use_status: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    polling_interval_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    license_note: Mapped[str] = mapped_column(Text, nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    contact_note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProviderRetrieval(Base):
    __tablename__ = "provider_retrievals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    normalized_record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    circuit_state: Mapped[str] = mapped_column(String(40), nullable=False, default="closed")
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acquisition_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    authorization_basis: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)


class RawSnapshot(Base):
    __tablename__ = "raw_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    retrieval_id: Mapped[str] = mapped_column(
        ForeignKey("provider_retrievals.id"), unique=True, nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_reference: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LegalApproval(Base):
    __tablename__ = "legal_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False)


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("provider_retrievals.id"), nullable=True, index=True
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProviderHealth(Base):
    __tablename__ = "provider_health"
    __table_args__ = (UniqueConstraint("provider_id", name="uq_provider_health_provider"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    last_successful_retrieval: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_changed_retrieval: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    circuit_state: Mapped[str] = mapped_column(String(40), nullable=False, default="closed")
    schema_drift_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_retrieval_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    schema_alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    known_status_note: Mapped[str] = mapped_column(Text, nullable=False)


class ParserVersion(Base):
    __tablename__ = "parser_versions"
    __table_args__ = (
        UniqueConstraint("provider_id", "version", name="uq_parser_versions_provider_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    format: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_fields: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    required_fields: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SchemaAlert(Base):
    __tablename__ = "schema_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    retrieval_id: Mapped[str] = mapped_column(
        ForeignKey("provider_retrievals.id"), index=True, nullable=False
    )
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    observed_fields: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    missing_required_fields: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    unexpected_fields: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RawDispatchRow(Base):
    __tablename__ = "raw_dispatch_rows"
    __table_args__ = (
        UniqueConstraint("raw_snapshot_id", "row_number", name="uq_raw_dispatch_rows_snapshot_row"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    raw_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("raw_snapshots.id"), index=True, nullable=False
    )
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DispatchObservation(Base):
    __tablename__ = "dispatch_observations"
    __table_args__ = (
        UniqueConstraint("raw_dispatch_row_id", name="uq_dispatch_observations_raw_row"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    raw_dispatch_row_id: Mapped[str] = mapped_column(
        ForeignKey("raw_dispatch_rows.id"), nullable=False
    )
    raw_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("raw_snapshots.id"), index=True, nullable=False
    )
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    source_case_number: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    agency: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    station: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    event_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    original_event_type: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_event_family: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    original_location: Mapped[str] = mapped_column(Text, nullable=False)
    location_precision: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    grid: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    parser_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_payload_reference: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ImportErrorRecord(Base):
    __tablename__ = "import_errors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_job_id: Mapped[str] = mapped_column(
        ForeignKey("import_jobs.id"), index=True, nullable=False
    )
    row_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CanonicalIncident(Base):
    __tablename__ = "canonical_incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    classification_family: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    classification_version: Mapped[str] = mapped_column(String(80), nullable=False)
    classification_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_band: Mapped[str] = mapped_column(String(32), nullable=False)
    review_band: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_event_type: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    first_event_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_event_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canonical_location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    canonical_grid: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    canonical_agency: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    canonical_station: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    contradiction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    classification_explanation: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    current_explanation: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    review_signal_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_issued", server_default="not_issued"
    )
    review_signal_issued_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_signal_revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_signal_revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    merged_into_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("canonical_incidents.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class IncidentObservationLink(Base):
    __tablename__ = "incident_observation_links"
    __table_args__ = (
        UniqueConstraint(
            "incident_id",
            "observation_id",
            "is_current",
            name="uq_incident_observation_link_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("dispatch_observations.id"), index=True, nullable=False
    )
    raw_dispatch_row_id: Mapped[str] = mapped_column(
        ForeignKey("raw_dispatch_rows.id"), index=True, nullable=False
    )
    link_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    assignment_key: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, unique=True)
    decision_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IncidentAlias(Base):
    __tablename__ = "incident_aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("dispatch_observations.id"), index=True, nullable=False
    )
    alias_type: Mapped[str] = mapped_column(String(40), nullable=False)
    alias_value: Mapped[str] = mapped_column(String(200), nullable=False)
    collision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


Index(
    "uq_incident_alias_provider_source_record",
    IncidentAlias.provider_id,
    IncidentAlias.alias_type,
    IncidentAlias.alias_value,
    unique=True,
    sqlite_where=IncidentAlias.alias_type == "source_record_id",
    postgresql_where=IncidentAlias.alias_type == "source_record_id",
)


class IncidentMatchDecision(Base):
    __tablename__ = "incident_match_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("dispatch_observations.id"), index=True, nullable=False
    )
    candidate_incident_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=True
    )
    reference_observation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("dispatch_observations.id"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_band: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    features: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    explanation: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IncidentEvidence(Base):
    __tablename__ = "incident_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("dispatch_observations.id"), index=True, nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(24), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IncidentTimelineEvent(Base):
    __tablename__ = "incident_timeline_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prior_state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    new_state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_observation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("dispatch_observations.id"), nullable=True
    )
    details: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    actor_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IncidentMerge(Base):
    __tablename__ = "incident_merges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    survivor_incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    absorbed_incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    actor_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IncidentSplit(Base):
    __tablename__ = "incident_splits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    new_incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    moved_observation_ids: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    actor_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IncidentProcessingRun(Base):
    __tablename__ = "incident_processing_runs"
    __table_args__ = (UniqueConstraint("retrieval_id", name="uq_incident_processing_retrieval"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    retrieval_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("provider_retrievals.id"), index=True, nullable=True
    )
    acquisition_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    linkage_version: Mapped[str] = mapped_column(String(80), nullable=False)
    classification_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    linked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_incident_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contradiction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actor_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IncidentRespondingAgency(Base):
    __tablename__ = "responding_agencies"
    __table_args__ = (
        UniqueConstraint(
            "incident_id", "agency", "observation_id", name="uq_incident_agency_observation"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("dispatch_observations.id"), index=True, nullable=False
    )
    agency: Mapped[str] = mapped_column(String(120), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IncidentRespondingStation(Base):
    __tablename__ = "responding_stations"
    __table_args__ = (
        UniqueConstraint(
            "incident_id", "station", "observation_id", name="uq_incident_station_observation"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("dispatch_observations.id"), index=True, nullable=False
    )
    station: Mapped[str] = mapped_column(String(200), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IncidentDisposition(Base):
    __tablename__ = "incident_dispositions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    observation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("dispatch_observations.id"), index=True, nullable=True
    )
    disposition: Mapped[str] = mapped_column(String(120), nullable=False)
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)


class PropertyMappingProfile(Base):
    __tablename__ = "property_mapping_profiles"
    __table_args__ = (
        UniqueConstraint("provider_id", "name", name="uq_property_mapping_profile_provider_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    mapping: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PropertyImport(Base):
    __tablename__ = "property_imports"
    __table_args__ = (
        UniqueConstraint("provider_id", "idempotency_key", name="uq_property_import_provider_key"),
        UniqueConstraint("provider_id", "content_hash", name="uq_property_import_provider_hash"),
        Index(
            "uq_property_import_current_provider",
            "provider_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
            postgresql_where=text("is_current = true"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    mapping_profile_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("property_mapping_profiles.id"), nullable=True
    )
    previous_import_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("property_imports.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    import_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(320), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source_version: Mapped[str] = mapped_column(String(120), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    acquisition_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    authorization_basis: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload_reference: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    removed_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)


class PropertyImportError(Base):
    __tablename__ = "property_import_errors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    property_import_id: Mapped[str] = mapped_column(
        ForeignKey("property_imports.id"), index=True, nullable=False
    )
    row_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PropertySourceRow(Base):
    __tablename__ = "property_source_rows"
    __table_args__ = (
        UniqueConstraint("property_import_id", "row_number", name="uq_property_source_import_row"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    property_import_id: Mapped[str] = mapped_column(
        ForeignKey("property_imports.id"), index=True, nullable=False
    )
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_parcel_id: Mapped[Optional[str]] = mapped_column(String(160), index=True, nullable=True)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_fields: Mapped[Optional[dict[str, Any]]] = mapped_column(JsonType, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Parcel(Base):
    __tablename__ = "parcels"
    __table_args__ = (
        UniqueConstraint("provider_id", "parcel_id", name="uq_parcel_provider_parcel_id"),
        Index("ix_parcels_address_search", "provider_id", "normalized_address"),
        Index("ix_parcels_street_search", "provider_id", "street_name", "house_number"),
        Index("ix_parcels_municipality_zip", "provider_id", "municipality", "postal_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    parcel_id: Mapped[str] = mapped_column(String(160), nullable=False)
    current_import_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("property_imports.id"), nullable=True
    )
    current_source_row_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("property_source_rows.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    source_version: Mapped[str] = mapped_column(String(120), nullable=False)
    effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    situs_original: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_address: Mapped[str] = mapped_column(Text, nullable=False)
    address_precision: Mapped[str] = mapped_column(String(40), nullable=False)
    house_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    street_prefix: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    street_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    street_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    street_suffix: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    municipality: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    county: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    geometry_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JsonType, nullable=True)
    grid: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    property_use_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    property_use_category: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    owner_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mailing_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year_built: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    effective_year_built: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    building_area: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    living_area: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    number_of_buildings: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    number_of_units: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stories: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    master_parcel_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    data_quality: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ParcelAddressAlias(Base):
    __tablename__ = "parcel_address_aliases"
    __table_args__ = (
        UniqueConstraint(
            "parcel_id", "normalized_address", "alias_type", name="uq_parcel_address_alias"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parcel_id: Mapped[str] = mapped_column(ForeignKey("parcels.id"), index=True, nullable=False)
    property_import_id: Mapped[str] = mapped_column(
        ForeignKey("property_imports.id"), index=True, nullable=False
    )
    alias_type: Mapped[str] = mapped_column(String(40), nullable=False)
    original_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_address: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PropertyBuilding(Base):
    __tablename__ = "property_buildings"
    __table_args__ = (
        UniqueConstraint("parcel_id", "building_key", name="uq_property_building_parcel_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parcel_id: Mapped[str] = mapped_column(ForeignKey("parcels.id"), index=True, nullable=False)
    property_import_id: Mapped[str] = mapped_column(
        ForeignKey("property_imports.id"), index=True, nullable=False
    )
    building_key: Mapped[str] = mapped_column(String(120), nullable=False)
    unit_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stories: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    building_area: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    footprint_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PropertyFieldValue(Base):
    __tablename__ = "property_field_values"
    __table_args__ = (
        UniqueConstraint(
            "property_import_id", "parcel_id", "field_name", name="uq_property_field_import_parcel"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    property_import_id: Mapped[str] = mapped_column(
        ForeignKey("property_imports.id"), index=True, nullable=False
    )
    parcel_id: Mapped[str] = mapped_column(ForeignKey("parcels.id"), index=True, nullable=False)
    source_row_id: Mapped[str] = mapped_column(
        ForeignKey("property_source_rows.id"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transformation: Mapped[str] = mapped_column(String(120), nullable=False)
    transformation_version: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    available_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IncidentPropertyMatchRun(Base):
    __tablename__ = "incident_property_match_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    property_provider_id: Mapped[str] = mapped_column(
        ForeignKey("providers.id"), index=True, nullable=False
    )
    property_import_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("property_imports.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    matcher_version: Mapped[str] = mapped_column(String(80), nullable=False)
    address_normalization_version: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    abstention_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_observation_ids: Mapped[list[str]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class IncidentPropertyCandidate(Base):
    __tablename__ = "incident_property_candidates"
    __table_args__ = (
        UniqueConstraint("match_run_id", "parcel_id", name="uq_property_candidate_run_parcel"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    match_run_id: Mapped[str] = mapped_column(
        ForeignKey("incident_property_match_runs.id"), index=True, nullable=False
    )
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    parcel_id: Mapped[str] = mapped_column(ForeignKey("parcels.id"), index=True, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    score_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    classification: Mapped[str] = mapped_column(String(24), nullable=False)
    recommendation_status: Mapped[str] = mapped_column(String(24), nullable=False)
    is_abstained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supporting_evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    contradictory_evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    features: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    explanation: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    property_data_quality: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PropertyMatchFeature(Base):
    __tablename__ = "property_match_features"
    __table_args__ = (
        UniqueConstraint("candidate_id", "feature_name", name="uq_property_match_feature_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("incident_property_candidates.id"), index=True, nullable=False
    )
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False)
    numeric_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    text_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contribution: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    available_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    feature_version: Mapped[str] = mapped_column(String(80), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PropertyMatchDecision(Base):
    __tablename__ = "property_match_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    candidate_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("incident_property_candidates.id"), nullable=True
    )
    parcel_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("parcels.id"), index=True, nullable=True
    )
    match_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("incident_property_match_runs.id"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    corrected_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScoringVersion(Base):
    __tablename__ = "scoring_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    component_versions: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    priors: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    rules: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OpportunityScoreRun(Base):
    __tablename__ = "opportunity_score_runs"
    __table_args__ = (
        Index(
            "uq_opportunity_score_current_incident",
            "incident_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
            postgresql_where=text("is_current = true"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    property_match_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("incident_property_match_runs.id"), nullable=True
    )
    property_provider_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("providers.id"), index=True, nullable=True
    )
    scoring_version: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_score_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("opportunity_score_runs.id"), nullable=True
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provisional_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    alert_eligibility: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    abstention_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hard_gate_status: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    source_observation_ids: Mapped[list[str]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    available_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)


class OpportunityScoreFeature(Base):
    __tablename__ = "opportunity_score_features"
    __table_args__ = (
        UniqueConstraint("score_run_id", "feature_name", name="uq_opportunity_score_feature_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    score_run_id: Mapped[str] = mapped_column(
        ForeignKey("opportunity_score_runs.id"), index=True, nullable=False
    )
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    contribution: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    source_observation_ids: Mapped[list[str]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    available_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    feature_version: Mapped[str] = mapped_column(String(80), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OpportunityScoreOverride(Base):
    __tablename__ = "opportunity_score_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    score_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("opportunity_score_runs.id"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InternalAlert(Base):
    __tablename__ = "internal_alerts"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_internal_alert_dedupe_key"),
        Index("ix_internal_alert_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    score_run_id: Mapped[str] = mapped_column(
        ForeignKey("opportunity_score_runs.id"), index=True, nullable=False
    )
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    suppression_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    snoozed_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class NotificationJob(Base):
    __tablename__ = "notification_jobs"
    __table_args__ = (
        UniqueConstraint("alert_id", "channel", name="uq_notification_alert_channel"),
        CheckConstraint("channel = 'in_app'", name="ck_notification_jobs_in_app"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alert_id: Mapped[str] = mapped_column(
        ForeignKey("internal_alerts.id"), index=True, nullable=False
    )
    channel: Mapped[str] = mapped_column(String(24), nullable=False, default="in_app")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IncidentAssignment(Base):
    __tablename__ = "incident_assignments"
    __table_args__ = (
        Index(
            "uq_incident_assignment_current",
            "incident_id",
            unique=True,
            sqlite_where=text("ended_at IS NULL"),
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    assignee_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="reviewer")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkflowNote(Base):
    __tablename__ = "workflow_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_incidents.id"), index=True, nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str] = mapped_column(String(40), nullable=False, default="review")
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ClientImport(Base):
    __tablename__ = "client_imports"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_client_import_idempotency"),
        UniqueConstraint("content_hash", name="uq_client_import_content_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(320), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    accepted_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_payload_reference: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExistingClientRecord(Base):
    __tablename__ = "existing_client_records"
    __table_args__ = (
        UniqueConstraint("client_import_id", "row_number", name="uq_client_import_row"),
        Index("ix_existing_client_address", "normalized_address"),
        Index("ix_existing_client_parcel", "parcel_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_import_id: Mapped[str] = mapped_column(
        ForeignKey("client_imports.id"), index=True, nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    client_key: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parcel_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
