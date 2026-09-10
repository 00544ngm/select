from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.job_service import JobService
from backend.application.local_queue import LocalQueueRepository
from backend.application.provider_clients import (
    ProviderConnectionTester,
    ProviderModelVerifier,
)
from backend.application.provider_service import ProviderService
from backend.application.queue import ArqJobQueue, JobQueue, SqliteJobQueue
from backend.config import database_connection_url, get_backend_settings
from backend.db.provider_repository import (
    GroupProviderRepository,
    ProviderConfigurationRepository,
)
from backend.db.auth_repository import ApiGroupRepository, UserRepository
from backend.db.repositories import JobRepository
from backend.db.session import SessionFactory, get_session
from backend.security.provider_crypto import ProviderCrypto
from backend.security.provider_crypto_factory import create_provider_crypto


async def get_job_repository(
    session: AsyncSession = Depends(get_session),
) -> JobRepository:
    return JobRepository(session)


async def get_provider_repository(
    session: AsyncSession = Depends(get_session),
) -> ProviderConfigurationRepository:
    return ProviderConfigurationRepository(session)


async def get_user_repository(
    session: AsyncSession = Depends(get_session),
) -> UserRepository:
    return UserRepository(session)


async def get_api_group_repository(
    session: AsyncSession = Depends(get_session),
) -> ApiGroupRepository:
    return ApiGroupRepository(session)


def get_provider_crypto():
    settings = get_backend_settings()
    return create_provider_crypto(settings)


async def get_provider_service(
    repository: ProviderConfigurationRepository = Depends(get_provider_repository),
    crypto: ProviderCrypto = Depends(get_provider_crypto),
) -> ProviderService:
    return ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=ProviderConnectionTester(),
        model_verifier=ProviderModelVerifier(),
    )


async def get_job_queue() -> AsyncIterator[JobQueue]:
    settings = get_backend_settings()
    if settings.runtime_mode == "desktop":
        database = database_connection_url(settings).database
        if not database:
            raise RuntimeError("Desktop SQLite database path is missing")
        yield SqliteJobQueue(
            LocalQueueRepository(SessionFactory, live_database=Path(database))
        )
        return
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        yield ArqJobQueue(pool)
    finally:
        await pool.aclose()


def build_provider_service(
    repository: ProviderConfigurationRepository | GroupProviderRepository,
) -> ProviderService:
    return ProviderService(
        repository=repository,
        crypto=get_provider_crypto(),
        connection_test=ProviderConnectionTester(),
        model_verifier=ProviderModelVerifier(),
    )


async def get_job_service(
    repository: JobRepository = Depends(get_job_repository),
    queue: JobQueue = Depends(get_job_queue),
    provider_service: ProviderService = Depends(get_provider_service),
    session: AsyncSession = Depends(get_session),
) -> JobService:
    def _group_service(scope: str) -> ProviderService:
        group_id = UUID(scope)
        return build_provider_service(
            GroupProviderRepository(session, api_group_id=group_id)
        )

    async def scope_available(
        provider: str, model: str | None, scope: str
    ) -> bool:
        return await _group_service(scope).is_model_available(provider, model)

    async def scope_used(provider: str, model: str | None, scope: str) -> None:
        await _group_service(scope).record_model_usage(provider, model)

    return JobService(
        repository=repository,
        queue=queue,
        provider_available=provider_service.is_model_available,
        model_used=provider_service.record_model_usage,
        scope_provider_available=scope_available,
        scope_model_used=scope_used,
    )


async def get_browser() -> AsyncIterator[Any]:
    """Provide a shared Playwright browser instance."""
    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    settings = get_backend_settings()
    if settings.runtime_mode == "desktop":
        from backend.desktop.browser_paths import resolve_browser_candidates

        browser = None
        last_error: Exception | None = None
        for candidate in resolve_browser_candidates():
            try:
                browser = await p.chromium.launch(
                    executable_path=str(candidate.executable),
                    headless=True,
                    args=["--no-sandbox"],
                )
                break
            except Exception as error:  # noqa: BLE001 - try the next browser candidate
                last_error = error
        if browser is None:
            await p.stop()
            raise RuntimeError("DESKTOP_BROWSER_START_FAILED") from last_error
    else:
        browser = await p.firefox.launch(headless=True, args=["--no-sandbox"])
    try:
        yield browser
    finally:
        await browser.close()
        await p.stop()


__all__ = [
    "get_api_group_repository",
    "get_browser",
    "get_job_queue",
    "get_job_repository",
    "get_job_service",
    "get_provider_crypto",
    "get_provider_repository",
    "get_provider_service",
    "get_user_repository",
]
