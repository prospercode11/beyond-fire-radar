from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BootstrapStatus(BaseModel):
    user_count: int
    available: bool


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    roles: List[str]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse


class ProviderResponse(BaseModel):
    id: str
    name: str
    source_authority: str
    geographic_coverage: str
    data_type: str
    authorized_use_status: str
    enabled: bool
    schema_version: str
    parser_version: str
    limitations: str


class ProviderListResponse(BaseModel):
    providers: list[ProviderResponse]


class ProviderHealthResponse(BaseModel):
    provider_id: str
    last_successful_retrieval: Optional[datetime]
    last_changed_retrieval: Optional[datetime]
    last_snapshot_hash: Optional[str]
    last_retrieval_status: Optional[str]
    failure_count: int
    circuit_state: str
    schema_drift_detected: bool
    schema_alert_count: int
    known_status_note: str


class ParserVersionResponse(BaseModel):
    provider_id: str
    version: str
    format: str
    expected_fields: List[str]
    required_fields: List[str]
    active: bool


class ImportJobResponse(BaseModel):
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


class SchemaAlertResponse(BaseModel):
    id: str
    retrieval_id: str
    provider_id: str
    parser_version: str
    severity: str
    code: str
    observed_fields: List[str]
    missing_required_fields: List[str]
    unexpected_fields: List[str]
    message: str
    created_at: datetime


class ObservationResponse(BaseModel):
    id: str
    raw_dispatch_row_id: str
    source_record_id: str
    source_event_id: Optional[str]
    source_case_number: Optional[str]
    agency: Optional[str]
    station: Optional[str]
    event_time: Optional[datetime]
    retrieved_at: datetime
    original_event_type: str
    normalized_event_family: str
    original_location: str
    grid: Optional[str]
    parser_confidence: float
    parser_version: str
    taxonomy_version: str
    raw_payload_reference: str


class ImportErrorResponse(BaseModel):
    id: str
    import_job_id: str
    row_number: Optional[int]
    code: str
    message: str


class ParserComparisonResponse(BaseModel):
    retrieval_id: str
    parser_version: str
    schema_version: str
    format: str
    normalized_record_count: int
    rejected_record_count: int
    schema_alerts: List[str]


class AuditResponse(BaseModel):
    id: str
    actor_user_id: Optional[str]
    action: str
    resource_type: str
    resource_id: Optional[str]
    request_id: str
    metadata: Dict[str, Any]
    created_at: datetime
