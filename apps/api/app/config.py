from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Beyond Fire Radar"
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = "sqlite:///./data/beyond_fire_radar.db"
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_hours: int = Field(default=8, ge=1, le=168)
    enable_live_sarasota_dispatch_polling: bool = False
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "change-me-in-development"
    web_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
