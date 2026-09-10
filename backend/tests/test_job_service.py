from __future__ import annotations

from types import SimpleNamespace
from typing import get_args
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import backend.api.schemas.jobs as job_schemas
from backend.api.schemas.jobs import (
    BatchJobCreate,
    HypothesisJobCreate,
    JudgmentJobCreate,
)
from backend.application.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from backend.application.job_service import JobService

VALID_URL = "https://www.walmart.com/ip/example/12345"


def test_task_provider_type_is_limited_to_primary_provider_slots():
    assert get_args(job_schemas.TaskProvider) == (
        "openai",
        "custom",
        "claude",
    )


@pytest.mark.parametrize("provider", ["cattoken", "cattoken_claude"])
def test_job_schema_rejects_retired_cattoken_provider(provider):
    with pytest.raises(ValueError):
        HypothesisJobCreate(url=VALID_URL, provider=provider)


@pytest.mark.asyncio
async def test_submit_persists_before_enqueueing():
    job = SimpleNamespace(id=uuid4(), status="queued")
    repository = AsyncMock()
    repository.create.return_value = job
    queue = AsyncMock()
    service = JobService(
        repository=repository,
        queue=queue,
        revision_provider=lambda: "abc1234",
    )

    result = await service.submit_hypothesis(HypothesisJobCreate(url=VALID_URL))

    assert result is job
    repository.create.assert_awaited_once_with(
        mode="hypothesis",
        request_payload={
            "url": VALID_URL,
            "expected_model_version": "combination_model_v2.1",
            "requested_at_revision": "abc1234",
        },
        name=None,
        retry_of_id=None,
    )
    queue.enqueue.assert_awaited_once_with("run_analysis_job", str(job.id))
    assert repository.create.await_count == 1
    assert queue.enqueue.await_count == 1


@pytest.mark.asyncio
async def test_submit_persists_enabled_rotation_snapshot():
    job = SimpleNamespace(id=uuid4(), status="queued")
    repository = AsyncMock()
    repository.create.return_value = job
    queue = AsyncMock()
    service = JobService(repository=repository, queue=queue)

    await service.submit_hypothesis(
        HypothesisJobCreate(
            url=VALID_URL,
            provider="openai",
            model="gpt-5.6",
            rotation_enabled=True,
            rotation_candidates=[
                {"provider": "openai", "model": "gpt-5.6"},
                {"provider": "openai", "model": "gpt-5.5"},
            ],
        )
    )

    payload = repository.create.await_args.kwargs["request_payload"]
    assert payload["rotation_enabled"] is True
    assert [item["model"] for item in payload["rotation_candidates"]] == [
        "gpt-5.6",
        "gpt-5.5",
    ]
    assert payload["rotation_snapshot_version"] == 1


@pytest.mark.asyncio
async def test_submit_records_model_usage_only_after_enqueue_succeeds():
    job = SimpleNamespace(id=uuid4(), status="queued")
    repository = AsyncMock()
    repository.create.return_value = job
    queue = AsyncMock()
    provider_available = AsyncMock(return_value=True)
    model_used = AsyncMock()
    service = JobService(
        repository=repository,
        queue=queue,
        provider_available=provider_available,
        model_used=model_used,
    )

    await service.submit_hypothesis(
        HypothesisJobCreate(
            url=VALID_URL,
            provider="openai",
            model="gpt-5.6-sol",
        )
    )

    queue.enqueue.assert_awaited_once()
    model_used.assert_awaited_once_with("openai", "gpt-5.6-sol")


@pytest.mark.asyncio
async def test_enqueue_failure_does_not_record_model_usage():
    job = SimpleNamespace(id=uuid4(), status="queued")
    repository = AsyncMock()
    repository.create.return_value = job
    queue = AsyncMock()
    queue.enqueue.side_effect = RuntimeError("queue unavailable")
    model_used = AsyncMock()
    service = JobService(
        repository=repository,
        queue=queue,
        provider_available=AsyncMock(return_value=True),
        model_used=model_used,
    )

    with pytest.raises(ServiceUnavailableError):
        await service.submit_hypothesis(
            HypothesisJobCreate(
                url=VALID_URL,
                provider="openai",
                model="gpt-5.6-sol",
            )
        )

    model_used.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_still_succeeds_when_model_usage_recording_fails():
    job = SimpleNamespace(id=uuid4(), status="queued")
    repository = AsyncMock()
    repository.create.return_value = job
    queue = AsyncMock()
    model_used = AsyncMock(side_effect=RuntimeError("usage telemetry unavailable"))
    service = JobService(
        repository=repository,
        queue=queue,
        model_used=model_used,
    )

    result = await service.submit_hypothesis(
        HypothesisJobCreate(url=VALID_URL, provider="openai", model="gpt-5.6-sol")
    )

    assert result is job
    queue.enqueue.assert_awaited_once_with("run_analysis_job", str(job.id))
    model_used.assert_awaited_once_with("openai", "gpt-5.6-sol")


@pytest.mark.asyncio
async def test_enqueue_failure_marks_durable_job_failed():
    job = SimpleNamespace(id=uuid4(), status="queued")
    repository = AsyncMock()
    repository.create.return_value = job
    queue = AsyncMock()
    queue.enqueue.side_effect = RuntimeError("redis unavailable")
    service = JobService(
        repository=repository,
        queue=queue,
        revision_provider=lambda: "abc1234",
    )

    with pytest.raises(ServiceUnavailableError) as error:
        await service.submit_hypothesis(HypothesisJobCreate(url=VALID_URL))

    assert error.value.code == "QUEUE_UNAVAILABLE"
    assert error.value.retryable is True
    repository.fail.assert_awaited_once_with(
        job.id,
        code="QUEUE_UNAVAILABLE",
        message="Task queue is unavailable",
    )


@pytest.mark.asyncio
async def test_submit_judgment_uses_judgment_mode():
    job = SimpleNamespace(id=uuid4(), status="queued")
    repository = AsyncMock()
    repository.create.return_value = job
    queue = AsyncMock()
    service = JobService(
        repository=repository,
        queue=queue,
        revision_provider=lambda: "abc1234",
    )

    result = await service.submit_judgment(
        JudgmentJobCreate(
            a_url="https://www.walmart.com/ip/example/12345",
            b_urls=["https://www.amazon.com/dp/B000000001"],
        )
    )

    assert result is job
    repository.create.assert_awaited_once_with(
        mode="judgment",
        request_payload={
            "a_url": "https://www.walmart.com/ip/example/12345",
            "b_urls": ["https://www.amazon.com/dp/B000000001"],
        },
        name=None,
        retry_of_id=None,
    )
    queue.enqueue.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.skip(reason="CatToken providers are rejected by the task schema")
async def test_submit_persists_cattoken_claude_provider_identity():
    job = SimpleNamespace(id=uuid4(), status="queued")
    repository = AsyncMock()
    repository.create.return_value = job
    queue = AsyncMock()
    provider_available = AsyncMock(return_value=True)
    service = JobService(
        repository=repository,
        queue=queue,
        provider_available=provider_available,
        revision_provider=lambda: "abc1234",
    )

    result = await service.submit_hypothesis(
        HypothesisJobCreate(
            url=VALID_URL,
            provider="cattoken_claude",
            model="claude-sonnet-4-6",
        )
    )

    assert result is job
    provider_available.assert_awaited_once_with("cattoken_claude", "claude-sonnet-4-6")
    repository.create.assert_awaited_once_with(
        mode="hypothesis",
        request_payload={
            "url": VALID_URL,
            "provider": "cattoken_claude",
            "model": "claude-sonnet-4-6",
            "expected_model_version": "combination_model_v2.1",
            "requested_at_revision": "abc1234",
        },
        name=None,
        retry_of_id=None,
    )


@pytest.mark.asyncio
async def test_submit_batch_uses_batch_mode():
    job = SimpleNamespace(id=uuid4(), status="queued")
    repository = AsyncMock()
    repository.create.return_value = job
    queue = AsyncMock()
    service = JobService(
        repository=repository,
        queue=queue,
        revision_provider=lambda: "abc1234",
    )

    result = await service.submit_batch(
        BatchJobCreate(urls=["https://www.walmart.com/ip/example/12345"])
    )

    assert result is job
    repository.create.assert_awaited_once_with(
        mode="batch",
        request_payload={
            "urls": ["https://www.walmart.com/ip/example/12345"],
            "expected_model_version": "combination_model_v2.1",
            "requested_at_revision": "abc1234",
        },
        name=None,
        retry_of_id=None,
    )
    queue.enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_creates_linked_job():
    job = SimpleNamespace(
        id=uuid4(),
        status="queued",
    )
    original = SimpleNamespace(
        id=uuid4(),
        status="failed",
        mode="hypothesis",
        request_payload={"url": "https://www.walmart.com/ip/example/12345"},
    )
    repository = AsyncMock()
    repository.get.return_value = original
    repository.create.return_value = job
    queue = AsyncMock()
    service = JobService(
        repository=repository,
        queue=queue,
        revision_provider=lambda: "abc1234",
    )

    result = await service.retry(original.id)

    assert result is job
    repository.create.assert_awaited_once_with(
        mode="hypothesis",
        request_payload={
            "url": "https://www.walmart.com/ip/example/12345",
            "expected_model_version": "combination_model_v2.1",
            "requested_at_revision": "abc1234",
        },
        name=None,
        retry_of_id=original.id,
    )


@pytest.mark.asyncio
async def test_retry_accepts_interrupted_job():
    job = SimpleNamespace(id=uuid4(), status="queued")
    original = SimpleNamespace(
        id=uuid4(),
        status="interrupted",
        mode="hypothesis",
        request_payload={"url": VALID_URL},
    )
    repository = AsyncMock()
    repository.get.return_value = original
    repository.create.return_value = job
    queue = AsyncMock()
    service = JobService(repository=repository, queue=queue)

    result = await service.retry(original.id)

    assert result is job
    repository.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_cattoken_llm_failure_keeps_selected_provider():
    job = SimpleNamespace(id=uuid4(), status="queued")
    original = SimpleNamespace(
        id=uuid4(),
        status="failed",
        mode="hypothesis",
        error_code="LLM_FAILED",
        error_message=(
            "CatToken structured output failed: Error code: 502 - "
            "Upstream access forbidden"
        ),
        request_payload={
            "url": VALID_URL,
            "provider": "cattoken",
            "model": "gpt-5.5",
        },
    )
    repository = AsyncMock()
    repository.get.return_value = original
    repository.create.return_value = job
    queue = AsyncMock()
    provider_available = AsyncMock(return_value=True)
    service = JobService(
        repository=repository,
        queue=queue,
        provider_available=provider_available,
        revision_provider=lambda: "newrev1",
    )

    result = await service.retry(original.id)

    assert result is job
    provider_available.assert_awaited_once_with("cattoken", "gpt-5.5")
    repository.create.assert_awaited_once_with(
        mode="hypothesis",
        request_payload={
            "url": VALID_URL,
            "provider": "cattoken",
            "model": "gpt-5.5",
            "expected_model_version": "combination_model_v2.1",
            "requested_at_revision": "newrev1",
        },
        name=None,
        retry_of_id=original.id,
    )


@pytest.mark.asyncio
async def test_retry_old_batch_applies_current_runtime_contract():
    job = SimpleNamespace(id=uuid4(), status="queued")
    original = SimpleNamespace(
        id=uuid4(),
        status="failed",
        mode="batch",
        request_payload={
            "urls": [VALID_URL],
            "expected_model_version": "combination_model_v2.0",
            "requested_at_revision": "oldrev1",
        },
    )
    repository = AsyncMock()
    repository.get.return_value = original
    repository.create.return_value = job
    queue = AsyncMock()
    service = JobService(
        repository=repository,
        queue=queue,
        revision_provider=lambda: "newrev1",
    )

    await service.retry(original.id)

    repository.create.assert_awaited_once_with(
        mode="batch",
        request_payload={
            "urls": [VALID_URL],
            "expected_model_version": "combination_model_v2.1",
            "requested_at_revision": "newrev1",
        },
        name=None,
        retry_of_id=original.id,
    )


@pytest.mark.asyncio
async def test_retry_missing_job_raises_not_found():
    repository = AsyncMock()
    repository.get.return_value = None
    queue = AsyncMock()
    service = JobService(repository=repository, queue=queue)

    with pytest.raises(NotFoundError):
        await service.retry(uuid4())


@pytest.mark.asyncio
async def test_retry_non_failed_job_raises_conflict():
    original = SimpleNamespace(id=uuid4(), status="running", mode="hypothesis")
    repository = AsyncMock()
    repository.get.return_value = original
    queue = AsyncMock()
    service = JobService(repository=repository, queue=queue)

    with pytest.raises(ConflictError) as error:
        await service.retry(original.id)

    assert error.value.code == "JOB_NOT_FAILED"


@pytest.mark.asyncio
async def test_submit_rejects_disabled_provider_before_creating_job():
    repository = AsyncMock()
    queue = AsyncMock()
    provider_available = AsyncMock(return_value=False)
    service = JobService(
        repository=repository,
        queue=queue,
        provider_available=provider_available,
    )

    with pytest.raises(ServiceUnavailableError) as error:
        await service.submit_hypothesis(
            HypothesisJobCreate(url=VALID_URL, provider="custom")
        )

    assert error.value.code == "PROVIDER_MODEL_NOT_VERIFIED"
    assert error.value.retryable is False
    provider_available.assert_awaited_once_with("custom", None)
    repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_defaults_provider_validation_to_openai():
    repository = AsyncMock()
    queue = AsyncMock()
    provider_available = AsyncMock(return_value=False)
    service = JobService(
        repository=repository,
        queue=queue,
        provider_available=provider_available,
    )

    with pytest.raises(ServiceUnavailableError):
        await service.submit_hypothesis(HypothesisJobCreate(url=VALID_URL))

    provider_available.assert_awaited_once_with("openai", None)
