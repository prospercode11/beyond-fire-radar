from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
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
