from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url


class BackendSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    runtime_mode: Literal["server", "desktop"] = "server"
    database_url: str = (
        "postgresql+asyncpg://bundling:bundling@127.0.0.1:5432/bundling"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    artifact_dir: Path = Path("output/bundling")
    api_prefix: str = "/api/v1"
    provider_encryption_key: str | None = None
    provider_key_file: Path = Path("backend/.api-config.key")
    desktop_session_token: str | None = None
    desktop_database_path: Path | None = None
    # Web 版登录鉴权（server 模式）。desktop 模式不使用。
    auth_secret: str | None = None
    auth_token_ttl_seconds: int = 60 * 60 * 24 * 30
    admin_initial_password: str | None = None


@lru_cache
def get_backend_settings() -> BackendSettings:
    return BackendSettings()


def database_connection_url(settings: BackendSettings | None = None) -> URL:
    current = settings or get_backend_settings()
    if current.runtime_mode == "desktop" and current.desktop_database_path is not None:
        return URL.create(
            "sqlite+aiosqlite",
            database=current.desktop_database_path.resolve().as_posix(),
        )
    return make_url(current.database_url)


__all__ = ["BackendSettings", "database_connection_url", "get_backend_settings"]
