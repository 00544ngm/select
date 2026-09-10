from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from backend.application.local_queue import LocalQueueRepository
from backend.application.queue import SqliteJobQueue
from backend.db.engine import create_database_engine
from backend.db.models import LocalQueueItem
from backend.db.session import create_session_factory
from backend.desktop.migrations import upgrade_database_async


def test_queue_item_defaults() -> None:
    item = LocalQueueItem(function="run_analysis_job", arguments=["job-id"])

    assert item.status == "queued"
    assert item.attempts == 0
    assert item.cancel_requested is False


@pytest_asyncio.fixture
async def queue_repository(tmp_path):
    database = tmp_path / "queue.db"
    url = f"sqlite+aiosqlite:///{database.as_posix()}"
    await upgrade_database_async(url)
    engine = create_database_engine(url)
    repository = LocalQueueRepository(create_session_factory(engine))
    try:
        yield repository
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_two_workers_cannot_claim_same_item(queue_repository) -> None:
    item = await queue_repository.enqueue("run_analysis_job", "job-1")

    first, second = await asyncio.gather(
        queue_repository.claim_next("worker-a"),
        queue_repository.claim_next("worker-b"),
    )

    claimed = [value for value in (first, second) if value is not None]
    assert [value.id for value in claimed] == [item.id]
    assert claimed[0].attempts == 1


@pytest.mark.asyncio
async def test_queue_claims_fifo_and_records_terminal_states(queue_repository) -> None:
    first = await queue_repository.enqueue("run_analysis_job", "job-1")
    second = await queue_repository.enqueue("run_cross_review", "job-2")

    claimed_first = await queue_repository.claim_next("desktop")
    assert claimed_first is not None
    assert claimed_first.id == first.id
    completed = await queue_repository.complete(first.id)
    assert completed is not None
    assert completed.status == "completed"

    claimed_second = await queue_repository.claim_next("desktop")
    assert claimed_second is not None
    assert claimed_second.id == second.id
    failed = await queue_repository.fail(second.id)
    assert failed is not None
    assert failed.status == "failed"


@pytest.mark.asyncio
async def test_cancelled_queued_item_is_not_claimed(queue_repository) -> None:
    item = await queue_repository.enqueue("run_analysis_job", "job-1")
    cancelled = await queue_repository.request_cancel(item.id)

    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert await queue_repository.claim_next("desktop") is None


@pytest.mark.asyncio
async def test_sqlite_queue_persists_function_and_arguments(queue_repository) -> None:
    queue = SqliteJobQueue(queue_repository)

    await queue.enqueue("run_analysis_job", "job-1")

    claimed = await queue_repository.claim_next("desktop")
    assert claimed is not None
    assert claimed.function == "run_analysis_job"
    assert claimed.arguments == ["job-1"]


@pytest.mark.asyncio
async def test_sqlite_queue_rejects_unknown_handler(queue_repository) -> None:
    queue = SqliteJobQueue(queue_repository)

    with pytest.raises(ValueError, match="Unsupported local queue function"):
        await queue.enqueue("arbitrary_function", "job-1")
