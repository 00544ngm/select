from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.workers.local_worker import LocalWorker


@pytest.mark.asyncio
async def test_worker_executes_and_completes_one_item() -> None:
    item = SimpleNamespace(
        id=uuid4(), function="run_analysis_job", arguments=["job-1"]
    )
    repository = AsyncMock()
    repository.claim_next.return_value = item
    handler = AsyncMock()
    worker = LocalWorker(
        repository,
        {"run_analysis_job": handler},
        worker_id="desktop-1",
    )

    assert await worker.run_once() is True

    handler.assert_awaited_once_with({}, "job-1")
    repository.complete.assert_awaited_once_with(item.id)
    repository.fail.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_records_handler_failure_without_raising() -> None:
    item = SimpleNamespace(id=uuid4(), function="run_analysis_job", arguments=[])
    repository = AsyncMock()
    repository.claim_next.return_value = item
    handler = AsyncMock(side_effect=RuntimeError("sensitive details"))
    worker = LocalWorker(repository, {"run_analysis_job": handler})

    assert await worker.run_once() is True

    repository.fail.assert_awaited_once_with(item.id)
    repository.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_rejects_unknown_persisted_function() -> None:
    item = SimpleNamespace(id=uuid4(), function="unknown", arguments=[])
    repository = AsyncMock()
    repository.claim_next.return_value = item
    worker = LocalWorker(repository, {})

    assert await worker.run_once() is True
    repository.fail.assert_awaited_once_with(item.id)


@pytest.mark.asyncio
async def test_worker_returns_false_when_queue_is_empty() -> None:
    repository = AsyncMock()
    repository.claim_next.return_value = None
    worker = LocalWorker(repository, {})

    assert await worker.run_once() is False
