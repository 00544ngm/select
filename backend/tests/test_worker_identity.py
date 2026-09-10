from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.workers.runtime_identity import (
    WORKER_IDENTITY_KEY,
    WORKER_IDENTITY_TTL_SECONDS,
    refresh_worker_identity,
)
from backend.workers.settings import WorkerSettings


@pytest.mark.asyncio
async def test_worker_identity_records_contract_revision_and_ttl():
    redis = AsyncMock()
    ctx = {"redis": redis}

    with patch(
        "backend.workers.runtime_identity.runtime_revision",
        return_value="revision-123",
    ):
        await refresh_worker_identity(ctx)

    redis.set.assert_awaited_once()
    key, raw = redis.set.await_args.args
    identity = json.loads(raw)
    assert key == WORKER_IDENTITY_KEY
    assert redis.set.await_args.kwargs == {"ex": WORKER_IDENTITY_TTL_SECONDS}
    assert identity["model_version"] == "combination_model_v2.1"
    assert identity["revision"] == "revision-123"
    assert identity["started_at"]
    assert identity["worker_id"]


@pytest.mark.asyncio
async def test_worker_identity_heartbeat_preserves_process_identity():
    redis = AsyncMock()
    ctx = {"redis": redis}

    await refresh_worker_identity(ctx)
    first = json.loads(redis.set.await_args.args[1])
    redis.set.reset_mock()
    await refresh_worker_identity(ctx)
    second = json.loads(redis.set.await_args.args[1])

    assert first["started_at"] == second["started_at"]
    assert first["worker_id"] == second["worker_id"]
    assert redis.set.await_args.kwargs == {"ex": 30}


def test_worker_settings_registers_ten_second_identity_refresh():
    identity_jobs = [
        job
        for job in WorkerSettings.cron_jobs
        if job.coroutine is refresh_worker_identity
    ]

    assert len(identity_jobs) == 1
    assert identity_jobs[0].second == {0, 10, 20, 30, 40, 50}
