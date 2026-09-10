from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domain.dto import ProductDTO
from backend.db.base import Base
from backend.db.models import AnalysisJob
from backend.db.repositories import JobRepository


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as current_session:
        yield current_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_atomically_claim_job(session: AsyncSession):
    repository = JobRepository(session)
    job = await repository.create(
        mode="hypothesis",
        request_payload={"url": "https://walmart.com/ip/example/12345"},
    )

    assert isinstance(job, AnalysisJob)
    assert job.status == "queued"

    claimed = await repository.transition(job.id, expected="queued", target="running")
    duplicate_claim = await repository.transition(
        job.id,
        expected="queued",
        target="running",
    )

    assert claimed is not None
    assert claimed.status == "running"
    assert duplicate_claim is None


@pytest.mark.asyncio
async def test_fail_records_stable_error(session: AsyncSession):
    repository = JobRepository(session)
    job = await repository.create(mode="hypothesis", request_payload={"url": "test"})

    failed = await repository.fail(
        job.id,
        code="QUEUE_UNAVAILABLE",
        message="Task queue is unavailable",
    )

    assert failed is not None
    assert failed.status == "failed"
    assert failed.error_code == "QUEUE_UNAVAILABLE"
    assert failed.error_message == "Task queue is unavailable"


@pytest.mark.asyncio
async def test_runtime_notice_can_be_set_and_cleared_for_running_job(
    session: AsyncSession,
):
    repository = JobRepository(session)
    job = await repository.create(mode="hypothesis", request_payload={"url": "test"})
    await repository.transition(job.id, expected="queued", target="running")

    waiting = await repository.set_runtime_notice(
        job.id,
        code="WALMART_CAPTCHA_REQUIRED",
        message="Waiting for Walmart verification",
    )
    assert waiting is not None
    assert waiting.error_code == "WALMART_CAPTCHA_REQUIRED"
    assert waiting.error_message == "Waiting for Walmart verification"

    cleared = await repository.set_runtime_notice(job.id, code=None, message=None)

    assert cleared is not None
    assert cleared.status == "running"
    assert cleared.error_code is None
    assert cleared.error_message is None


@pytest.mark.asyncio
async def test_runtime_notice_does_not_modify_terminal_job(session: AsyncSession):
    repository = JobRepository(session)
    job = await repository.create(mode="hypothesis", request_payload={"url": "test"})
    await repository.fail(job.id, code="SCRAPE_FAILED", message="Original failure")

    updated = await repository.set_runtime_notice(
        job.id,
        code="WALMART_CAPTCHA_REQUIRED",
        message="Should not replace failure",
    )
    persisted = await repository.get(job.id)

    assert updated is None
    assert persisted is not None
    assert persisted.status == "failed"
    assert persisted.error_code == "SCRAPE_FAILED"
    assert persisted.error_message == "Original failure"


@pytest.mark.asyncio
async def test_set_progress_is_monotonic_for_running_job(session: AsyncSession):
    repository = JobRepository(session)
    job = await repository.create(mode="hypothesis", request_payload={"url": "test"})
    await repository.transition(job.id, expected="queued", target="running")

    updated = await repository.set_progress(job.id, 35)
    unchanged = await repository.set_progress(job.id, 20)

    assert updated is not None
    assert updated.progress == 35
    assert unchanged is not None
    assert unchanged.progress == 35


@pytest.mark.asyncio
async def test_rename_only_changes_job_name_and_version(session: AsyncSession):
    repository = JobRepository(session)
    job = await repository.create(
        mode="hypothesis",
        name="原名称",
        request_payload={"url": "test"},
    )
    await repository.transition(job.id, expected="queued", target="running")
    await repository.set_progress(job.id, 35)
    original = await repository.get(job.id)
    assert original is not None
    original_version = original.version

    renamed = await repository.rename(job.id, "采购复核")

    assert renamed is not None
    assert renamed.name == "采购复核"
    assert renamed.status == "running"
    assert renamed.progress == 35
    assert renamed.result_payload is None
    assert renamed.version == original_version + 1


@pytest.mark.asyncio
async def test_rename_returns_none_for_missing_job(session: AsyncSession):
    from uuid import uuid4

    assert await JobRepository(session).rename(uuid4(), None) is None


@pytest.mark.asyncio
async def test_list_returns_paginated_items(session: AsyncSession):
    repository = JobRepository(session)
    await repository.create(mode="hypothesis", request_payload={"url": "https://walmart.com/ip/a"})
    await repository.create(mode="judgment", request_payload={"url": "https://walmart.com/ip/b"})
    await repository.create(mode="hypothesis", request_payload={"url": "https://walmart.com/ip/c"})

    items, total = await repository.list(page=1, page_size=2)

    assert total == 3
    assert len(items) == 2


@pytest.mark.asyncio
async def test_list_filters_by_mode(session: AsyncSession):
    repository = JobRepository(session)
    await repository.create(mode="hypothesis", request_payload={"url": "https://walmart.com/ip/a"})
    await repository.create(mode="judgment", request_payload={"url": "https://walmart.com/ip/b"})
    await repository.create(mode="hypothesis", request_payload={"url": "https://walmart.com/ip/c"})

    items, total = await repository.list(page=1, page_size=10, mode="hypothesis")

    assert total == 2
    assert all(item.mode == "hypothesis" for item in items)


@pytest.mark.asyncio
async def test_list_orders_by_created_at_desc(session: AsyncSession):
    repository = JobRepository(session)
    await repository.create(mode="hypothesis", request_payload={"url": "https://walmart.com/ip/a"})
    await repository.create(mode="hypothesis", request_payload={"url": "https://walmart.com/ip/b"})

    items, _total = await repository.list(page=1, page_size=10)

    assert items[0].created_at >= items[-1].created_at


@pytest.mark.asyncio
async def test_list_empty_returns_zero(session: AsyncSession):
    repository = JobRepository(session)

    items, total = await repository.list(page=1, page_size=10)

    assert total == 0
    assert items == []


@pytest.mark.asyncio
async def test_get_artifact_returns_matching_record(session: AsyncSession):
    from backend.db.models import Artifact

    repository = JobRepository(session)
    job = await repository.create(mode="hypothesis", request_payload={"url": "https://walmart.com/ip/a"})

    artifact = Artifact(
        job_id=job.id,
        kind="json",
        path="/tmp/result.json",
        size=100,
        checksum="abc123",
    )
    session.add(artifact)
    await session.commit()

    found = await repository.get_artifact(job.id, "json")
    assert found is not None
    assert found.kind == "json"
    assert found.path == "/tmp/result.json"

    missing = await repository.get_artifact(job.id, "excel")
    assert missing is None


@pytest.mark.asyncio
async def test_attempt_repository_records_completion_and_lists_in_order(
    session: AsyncSession,
):
    repository = JobRepository(session)
    job = await repository.create(
        mode="hypothesis",
        request_payload={"url": "https://walmart.com/ip/a"},
    )

    first = await repository.create_attempt(
        job.id,
        ordinal=1,
        provider="openai",
        api_protocol="openai",
        model="gpt-5.6",
    )
    await repository.finish_attempt(
        first.id,
        status="failed",
        stage="schema",
        error_code="MODEL_SCHEMA_INVALID",
        error_message="模型报告结构无效",
    )
    await repository.create_attempt(
        job.id,
        ordinal=2,
        provider="openai",
        api_protocol="openai",
        model="gpt-5.5",
    )

    attempts = await repository.list_attempts(job.id)

    assert [attempt.ordinal for attempt in attempts] == [1, 2]
    assert attempts[0].status == "failed"
    assert attempts[0].error_code == "MODEL_SCHEMA_INVALID"
    assert attempts[0].duration_ms is not None


@pytest.mark.asyncio
async def test_product_snapshot_is_linked_to_job_without_changing_job_history(
    session: AsyncSession,
):
    repository = JobRepository(session)
    job = await repository.create(
        mode="hypothesis",
        request_payload={"url": "https://www.walmart.com/ip/example/12345"},
    )
    product = ProductDTO(
        url="https://www.walmart.com/ip/example/12345",
        product_id="12345",
        title="Example product",
        price="$19.99",
        bullet_points=["Durable"],
    )

    snapshot = await repository.create_product_snapshot(
        job.id, product, role="main", position=0
    )
    products = await repository.list_job_products(job.id)

    assert snapshot.scraped_data["title"] == "Example product"
    assert snapshot.platform == "walmart"
    assert len(products) == 1
    assert products[0][0].role == "main"
    assert products[0][1].id == snapshot.id
    historical = await repository.get(job.id)
    assert historical is not None
    assert historical.status == "queued"


@pytest.mark.asyncio
async def test_delete_attempt_removes_only_the_current_attempt(session: AsyncSession):
    repository = JobRepository(session)
    job = await repository.create(
        mode="hypothesis",
        request_payload={"url": "https://www.walmart.com/ip/example/12345"},
    )
    first = await repository.create_attempt(
        job.id,
        ordinal=1,
        provider="openai",
        api_protocol="openai",
        model="gpt-5.6",
    )
    second = await repository.create_attempt(
        job.id,
        ordinal=2,
        provider="openai",
        api_protocol="openai",
        model="gpt-5.5",
    )

    await repository.delete_attempt(second.id)

    attempts = await repository.list_attempts(job.id)
    assert [attempt.id for attempt in attempts] == [first.id]
    assert await repository.get(job.id) is not None
