from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Beyond Fire Radar"
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = "sqlite:///./data/beyond_fire_radar.db"
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_hours: int = Field(default=8, ge=1, le=168)
    session_idle_ttl_hours: int = Field(default=8, ge=1, le=168)
    enable_live_sarasota_dispatch_polling: bool = False
    enable_sarasota_polling_worker: bool = False
    sarasota_dispatch_url: str = "https://dispatchreporting.scgov.net/Events?strAgencyID=All"
    sarasota_poll_interval_seconds: int = Field(default=900, ge=900, le=900)
    sarasota_poll_timeout_seconds: int = Field(default=20, ge=5, le=60)
    sarasota_live_authorization_basis: Optional[str] = None
    enable_learned_model_serving: bool = False
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "change-me-in-development"
    enable_bootstrap: bool = True
    web_origin: str = "http://localhost:3000"
    allowed_hosts: str = "*"
    raw_snapshot_dir: str = "data/raw-snapshots"
    max_snapshot_bytes: int = Field(default=10_000_000, ge=1024, le=100_000_000)
    max_property_import_bytes: int = Field(default=25_000_000, ge=1024, le=200_000_000)
    max_client_import_bytes: int = Field(default=5_000_000, ge=1024, le=50_000_000)
    max_request_bytes: int = Field(default=30_000_000, ge=1024, le=250_000_000)
    max_archive_members: int = Field(default=100, ge=1, le=10_000)
    max_archive_uncompressed_bytes: int = Field(default=100_000_000, ge=1024, le=1_000_000_000)
    max_active_sessions: int = Field(default=5, ge=1, le=50)
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_login_requests: int = Field(default=10, ge=1, le=1000)
    rate_limit_upload_requests: int = Field(default=20, ge=1, le=1000)
    redis_required_for_readiness: bool = False
    raw_snapshot_backend: Literal["local", "s3"] = "local"
    object_storage_bucket: Optional[str] = None
    object_storage_endpoint_url: Optional[str] = None
    object_storage_region: str = "auto"
    object_storage_access_key_id: Optional[str] = None
    object_storage_secret_access_key: Optional[str] = None
    object_storage_prefix: str = "beyond-fire-radar/raw-snapshots"
    raw_snapshot_retention_days: int = Field(default=365, ge=1, le=36500)
    audit_retention_days: int = Field(default=2555, ge=1, le=36500)
    audit_chain_enabled: bool = True
    log_level: str = "INFO"
    error_tracking_dsn: Optional[str] = None
    enable_api_docs: bool = True

    @model_validator(mode="after")
    def validate_production_defaults(self) -> "Settings":
        if self.app_env.lower() in {"production", "staging"}:
            if self.enable_bootstrap:
                raise ValueError("ENABLE_BOOTSTRAP must be false outside development")
            if self.bootstrap_admin_password == "change-me-in-development":
                raise ValueError("BOOTSTRAP_ADMIN_PASSWORD must be replaced outside development")
            if self.database_url.startswith("sqlite"):
                raise ValueError("DATABASE_URL must use PostgreSQL outside development")
            origins = self.web_origins()
            if not origins or any(not origin.startswith("https://") for origin in origins):
                raise ValueError("every WEB_ORIGIN must use HTTPS outside development")
            if not self.allowed_hosts.strip() or "*" in self.allowed_hosts:
                raise ValueError("ALLOWED_HOSTS must explicitly list deployment hostnames")
            if self.rate_limit_backend != "redis":
                raise ValueError("RATE_LIMIT_BACKEND=redis is required outside development")
            if not self.redis_required_for_readiness:
                raise ValueError("REDIS_REQUIRED_FOR_READINESS must be true outside development")
            if self.enable_api_docs:
                raise ValueError("ENABLE_API_DOCS must be false outside development")
            if self.raw_snapshot_backend != "s3":
                raise ValueError("S3 raw snapshot storage is required outside development")
            required = (
                self.object_storage_bucket,
                self.object_storage_endpoint_url,
                self.object_storage_access_key_id,
                self.object_storage_secret_access_key,
            )
            if any(value in {None, ""} for value in required):
                raise ValueError(
                    "S3 raw snapshot storage requires complete object-storage settings"
                )
            endpoint = self.object_storage_endpoint_url
            if endpoint is None or not endpoint.startswith("https://"):
                raise ValueError("object storage endpoint must use HTTPS outside development")
        return self

    def web_origins(self) -> list[str]:
        return [origin.strip() for origin in self.web_origin.split(",") if origin.strip()]

    def allowed_hostnames(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
