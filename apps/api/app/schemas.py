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


class AuditResponse(BaseModel):
    id: str
    actor_user_id: Optional[str]
    action: str
    resource_type: str
    resource_id: Optional[str]
    request_id: str
    metadata: Dict[str, Any]
    created_at: datetime
