from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

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
    acquisition_mode: str
    authorization_basis: Optional[str]


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
    location_precision: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
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


class IncidentProcessResponse(BaseModel):
    processing_run_id: str
    retrieval_id: Optional[str]
    provider_id: str
    acquisition_mode: str
    status: str
    linkage_version: str
    classification_version: str
    observation_count: int
    linked_count: int
    new_incident_count: int
    review_count: int
    contradiction_count: int


class IncidentStateUpdate(BaseModel):
    state: str
    reason: str = Field(min_length=3, max_length=1000)


class IncidentMergeRequest(BaseModel):
    absorbed_incident_id: str
    reason: str = Field(min_length=3, max_length=1000)


class IncidentSplitRequest(BaseModel):
    observation_ids: List[str] = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=1000)


class IncidentSummaryResponse(BaseModel):
    id: str
    provider_id: str
    state: str
    classification_family: str
    classification_version: str
    classification_confidence: float
    confidence_band: str
    review_band: str
    first_event_time: Optional[datetime]
    last_event_time: Optional[datetime]
    canonical_location: Optional[str]
    contradiction_count: int
    review_signal_status: str
    review_signal_issued_at: Optional[datetime]
    review_signal_revoked_at: Optional[datetime]
    review_signal_revocation_reason: Optional[str]
    observation_count: int
    is_active: bool
    merged_into_id: Optional[str]


class IncidentDetailResponse(IncidentSummaryResponse):
    canonical_event_type: Optional[str]
    canonical_grid: Optional[str]
    canonical_agency: Optional[str]
    canonical_station: Optional[str]
    classification_explanation: Dict[str, Any]
    current_explanation: Dict[str, Any]
    source_acquisition_modes: List[str]
    source_retrieval_ids: List[str]
    observations: List[ObservationResponse]
    source_row_ids: List[str]
    relationship_history: List[Dict[str, Any]]
    timeline: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]
    match_decisions: List[Dict[str, Any]]
    aliases: List[Dict[str, Any]]


class PropertyMappingProfileCreate(BaseModel):
    provider_id: str
    name: str = Field(min_length=1, max_length=120)
    mapping: Dict[str, str]


class PropertyMappingProfileResponse(BaseModel):
    id: str
    provider_id: str
    name: str
    mapping: Dict[str, str]
    version: str
    created_at: datetime


class PropertyImportPreviewResponse(BaseModel):
    format: str
    headers: List[str]
    mapping: Dict[str, str]
    row_count: int
    rejected_row_count: int
    warnings: List[str]
    errors: List[str]
    sample_rows: List[Dict[str, Any]]


class PropertyImportResponse(BaseModel):
    property_import_id: str
    provider_id: str
    status: str
    format: str
    source_version: str
    content_hash: str
    normalized_row_count: int
    rejected_row_count: int
    removed_row_count: int
    replayed: bool
    mapping: Dict[str, str]
    warnings: List[str]
    errors: List[str]
    acquisition_mode: str
    authorization_basis: Optional[str]
    source_filename: Optional[str] = None
    parser_version: Optional[str] = None
    schema_version: Optional[str] = None
    effective_at: Optional[datetime] = None
    retrieved_at: Optional[datetime] = None
    raw_payload_reference: Optional[str] = None


class PropertyImportErrorResponse(BaseModel):
    id: str
    property_import_id: str
    row_number: Optional[int]
    code: str
    message: str
    raw_payload: Optional[str]


class PropertyCandidateResponse(BaseModel):
    id: str
    incident_id: str
    parcel_id: str
    rank: int
    match_score: float
    score_margin: Optional[float]
    classification: str
    recommendation_status: str
    is_abstained: bool
    supporting_evidence: List[Dict[str, Any]]
    contradictory_evidence: List[Dict[str, Any]]
    features: Dict[str, Any]
    explanation: Dict[str, Any]
    property_data_quality: Dict[str, Any]
    parcel: Dict[str, Any]


class PropertyMatchRunResponse(BaseModel):
    id: str
    incident_id: str
    property_provider_id: str
    property_import_id: Optional[str]
    status: str
    matcher_version: str
    address_normalization_version: str
    candidate_count: int
    abstention_reason: Optional[str]
    source_observation_ids: List[str]
    created_at: datetime
    completed_at: Optional[datetime]
    candidates: List[PropertyCandidateResponse]
    current_human_decision: Optional[Dict[str, Any]]


class PropertyMatchRunRequest(BaseModel):
    property_provider_id: str
    property_import_id: Optional[str] = None


class PropertyMatchDecisionRequest(BaseModel):
    decision: Literal["confirmed", "rejected", "cleared", "corrected"]
    reason: str = Field(min_length=3, max_length=1000)
    candidate_id: Optional[str] = None
    corrected_address: Optional[str] = Field(default=None, max_length=500)


class PropertyMatchDecisionResponse(BaseModel):
    id: str
    incident_id: str
    candidate_id: Optional[str]
    parcel_id: Optional[str]
    decision: str
    corrected_address: Optional[str]
    reason: str
    actor_user_id: str
    created_at: datetime


class ParcelResponse(BaseModel):
    id: str
    provider_id: str
    parcel_id: str
    is_active: bool
    source_version: str
    effective_at: Optional[datetime]
    situs_original: str
    normalized_address: str
    address_precision: str
    municipality: Optional[str]
    postal_code: Optional[str]
    property_use_code: Optional[str]
    property_use_category: Optional[str]
    owner_name: Optional[str]
    mailing_address: Optional[str]
    year_built: Optional[int]
    building_area: Optional[float]
    number_of_buildings: Optional[int]
    number_of_units: Optional[int]
    stories: Optional[int]
    latitude: Optional[float]
    longitude: Optional[float]
    master_parcel_id: Optional[str]
    data_quality: Dict[str, Any]
    current_import_id: Optional[str] = None
    current_source_row_id: Optional[str] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)
