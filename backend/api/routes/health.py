from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.runtime_contract import (
    EXPECTED_COMBINATION_MODEL_VERSION,
    runtime_revision,
)
from backend.config import get_backend_settings
from backend.db.session import SessionFactory
from backend.workers.runtime_identity import WORKER_IDENTITY_KEY

router = APIRouter(prefix="/health", tags=["health"])


async def check_database(timeout: float = 2.0) -> str:
    try:
        async with asyncio.timeout(timeout):
            async with SessionFactory() as session:
                await session.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # noqa: BLE001 - health probe must degrade dependency failures
        return "unavailable"


async def check_redis(timeout: float = 2.0) -> str:
    from arq import create_pool
    from arq.connections import RedisSettings

    settings = get_backend_settings()
    if settings.runtime_mode == "desktop":
        return "ok"
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    try:
        async with asyncio.timeout(timeout):
            pool = await create_pool(redis_settings)
            try:
                await pool.ping()
            finally:
                await pool.aclose()
        return "ok"
    except Exception:  # noqa: BLE001 - health probe must degrade dependency failures
        return "unavailable"


async def check_worker(timeout: float = 2.0) -> str:
    from arq import create_pool
    from arq.connections import RedisSettings

    settings = get_backend_settings()
    if settings.runtime_mode == "desktop":
        identity = await check_worker_identity(timeout)
        if not identity:
            return "unavailable"
        try:
            heartbeat = datetime.fromisoformat(str(identity["heartbeat_at"]))
        except (KeyError, TypeError, ValueError):
            return "unavailable"
        age = datetime.now(timezone.utc) - heartbeat.astimezone(timezone.utc)
        return "ok" if age.total_seconds() <= 15 else "unavailable"
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    try:
        async with asyncio.timeout(timeout):
            pool = await create_pool(redis_settings)
            try:
                info = await pool.get("arq:queue:health-check")
                return "ok" if info else "unavailable"
            finally:
                await pool.aclose()
    except Exception:  # noqa: BLE001 - health probe must degrade dependency failures
        return "unavailable"


async def check_worker_identity(timeout: float = 2.0) -> dict[str, Any] | None:
    from arq import create_pool
    from arq.connections import RedisSettings

    settings = get_backend_settings()
    if settings.runtime_mode == "desktop":
        from backend.desktop.paths import DesktopPaths
        from backend.workers.local_identity import read_local_worker_identity

        return read_local_worker_identity(
            DesktopPaths.for_current_user().worker_heartbeat_file
        )
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    try:
        async with asyncio.timeout(timeout):
            pool = await create_pool(redis_settings)
            try:
                raw = await pool.get(WORKER_IDENTITY_KEY)
            finally:
                await pool.aclose()
        if not raw:
            return None
        decoded = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        identity = json.loads(decoded)
        return identity if isinstance(identity, dict) else None
    except Exception:  # noqa: BLE001 - health probe must degrade dependency failures
        return None


async def check_desktop_runtime() -> str:
    settings = get_backend_settings()
    if settings.runtime_mode != "desktop":
        return "ok"
    probe: Path | None = None
    try:
        from backend.desktop.browser_paths import resolve_browser_candidates

        artifact_dir = settings.artifact_dir.resolve()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        probe = artifact_dir / f".write-probe-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        resolve_browser_candidates()
        return "ok"
    except Exception:  # noqa: BLE001 - readiness must not expose local paths
        return "unavailable"
    finally:
        if probe is not None:
            probe.unlink(missing_ok=True)


@router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=None)
async def readiness(
    database: str = Depends(check_database),
    redis: str = Depends(check_redis),
    worker: str = Depends(check_worker),
    worker_identity: dict[str, Any] | None = Depends(check_worker_identity),
    runtime: str = Depends(check_desktop_runtime),
) -> dict[str, str] | JSONResponse:
    api_version = EXPECTED_COMBINATION_MODEL_VERSION
    api_revision = runtime_revision()
    worker_version = (
        str(worker_identity.get("model_version", "unknown"))
        if worker_identity
        else "unavailable"
    )
    worker_revision = (
        str(worker_identity.get("revision", "unknown"))
        if worker_identity
        else "unavailable"
    )
    if not worker_identity:
        contract_match = "unavailable"
    elif worker_version != api_version or (
        api_revision != "unknown"
        and worker_revision != "unknown"
        and api_revision != worker_revision
    ):
        contract_match = "mismatch"
    else:
        contract_match = "ok"

    dependency_name = "queue" if get_backend_settings().runtime_mode == "desktop" else "redis"
    payload = {
        "database": database,
        dependency_name: redis,
        "worker": worker,
        "api_model_version": api_version,
        "worker_model_version": worker_version,
        "api_revision": api_revision,
        "worker_revision": worker_revision,
        "contract_match": contract_match,
        "runtime": runtime,
    }
    if any(value != "ok" for value in (database, redis, worker, contract_match, runtime)):
        return JSONResponse(status_code=503, content=payload)
    return payload


__all__ = ["router"]
