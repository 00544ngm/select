from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import (
    BrowserTargetClosedError,
    LLMError,
    WalmartCaptchaTimeoutError,
    WalmartNavigationTimeoutError,
    WalmartNetworkError,
)
from backend.application.analysis_runner import RunnerResult
from backend.config import BackendSettings
from backend.security.windows_dpapi import WindowsDPAPI
from backend.workers import jobs as worker_jobs


def _claimed_job(mode: str = "hypothesis", **kwargs):
    """Create a mock claimed job with proper attributes."""
    payload = kwargs.pop("request_payload", {"url": "https://walmart.com/ip/test"})
    mock = AsyncMock()
    mock.status = kwargs.pop("status", "running")
    mock.mode = mode
    mock.request_payload = payload
    for k, v in kwargs.items():
        setattr(mock, k, v)
    return mock


@pytest.fixture
def mock_ctx():
    return {"redis": AsyncMock()}


def _resolver_stub():
    resolver = AsyncMock()
    resolver.resolve_primary.return_value = SimpleNamespace(
        client=AsyncMock(),
        provider="openai",
        model="gpt-test",
    )
    resolver.resolve_secondary_deepseek.return_value = None
    return resolver


@pytest.mark.asyncio
async def test_browser_scrape_failure_does_not_create_model_attempt(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        request_payload={
            "url": "https://walmart.com/ip/test",
            "provider": "openai",
            "model": "gpt-5.6",
            "rotation_enabled": True,
            "rotation_candidates": [
                {"provider": "openai", "model": "gpt-5.6"},
                {"provider": "openai", "model": "gpt-5.5"},
            ],
        }
    )
    runner = AsyncMock()
    runner.scrape_hypothesis_product.side_effect = BrowserTargetClosedError()

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(
            worker_jobs,
            "_create_provider_resolver",
            return_value=_resolver_stub(),
        ),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {"status": "failed", "error_code": "BROWSER_TARGET_CLOSED"}
    repository.create_attempt.assert_not_awaited()
    runner.run_hypothesis.assert_not_awaited()
    repository.fail.assert_awaited_once()
    assert repository.fail.await_args.kwargs["code"] == "BROWSER_TARGET_CLOSED"


@pytest.mark.asyncio
async def test_walmart_captcha_timeout_records_notice_without_model_attempt(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job()
    runner = AsyncMock()

    async def scrape_with_timeout(*args, verification_status=None, **kwargs):
        assert verification_status is not None
        await verification_status(True)
        raise WalmartCaptchaTimeoutError()

    runner.scrape_hypothesis_product.side_effect = scrape_with_timeout

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(
            worker_jobs,
            "_create_provider_resolver",
            return_value=_resolver_stub(),
        ),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {
        "status": "failed",
        "error_code": "WALMART_CAPTCHA_TIMEOUT",
    }
    repository.set_runtime_notice.assert_awaited_once()
    notice = repository.set_runtime_notice.await_args.kwargs
    assert notice["code"] == "WALMART_CAPTCHA_REQUIRED"
    assert "模型尚未调用" in notice["message"]
    repository.create_attempt.assert_not_awaited()
    runner.run_hypothesis.assert_not_awaited()
    assert repository.fail.await_args.kwargs["code"] == "WALMART_CAPTCHA_TIMEOUT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scrape_error", "expected_code"),
    [
        (WalmartNavigationTimeoutError(), "WALMART_NAVIGATION_TIMEOUT"),
        (WalmartNetworkError(), "WALMART_NETWORK_FAILED"),
    ],
)
async def test_walmart_navigation_failures_do_not_enter_model_rotation(
    mock_ctx, scrape_error, expected_code
):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        request_payload={
            "url": "https://walmart.com/ip/test",
            "provider": "openai",
            "model": "gpt-5.6",
            "rotation_enabled": True,
            "rotation_candidates": [
                {"provider": "openai", "model": "gpt-5.6"},
                {"provider": "openai", "model": "gpt-5.5"},
            ],
        }
    )
    runner = AsyncMock()
    runner.scrape_hypothesis_product.side_effect = scrape_error
    resolver = _resolver_stub()

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=resolver) as create_resolver,
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {"status": "failed", "error_code": expected_code}
    repository.create_attempt.assert_not_awaited()
    repository.fail.assert_awaited_once()
    assert repository.fail.await_args.kwargs["code"] == expected_code
    create_resolver.assert_not_called()


@pytest.mark.asyncio
async def test_analysis_browser_start_failure_does_not_create_model_attempt(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job()
    runner = AsyncMock()
    runner.start_browser.side_effect = BrowserTargetClosedError()

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(
            worker_jobs,
            "_create_provider_resolver",
            return_value=_resolver_stub(),
        ),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {"status": "failed", "error_code": "BROWSER_TARGET_CLOSED"}
    repository.create_attempt.assert_not_awaited()


@pytest.mark.asyncio
async def test_browser_failure_during_analysis_is_not_kept_as_model_attempt(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job()
    runner = AsyncMock()
    runner.scrape_hypothesis_product.return_value = SimpleNamespace(
        url="https://walmart.com/ip/test", title="Product"
    )
    runner.run_hypothesis.side_effect = BrowserTargetClosedError()

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(
            worker_jobs,
            "_create_provider_resolver",
            return_value=_resolver_stub(),
        ),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {"status": "failed", "error_code": "BROWSER_TARGET_CLOSED"}
    repository.delete_attempt.assert_awaited_once()
    repository.finish_attempt.assert_not_awaited()


@pytest.mark.asyncio
async def test_model_rotation_reuses_one_scraped_product_snapshot(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        request_payload={
            "url": "https://walmart.com/ip/test/12345",
            "provider": "openai",
            "model": "gpt-5.6",
            "rotation_enabled": True,
            "rotation_candidates": [
                {"provider": "openai", "model": "gpt-5.6"},
                {"provider": "openai", "model": "gpt-5.5"},
            ],
        }
    )
    product = SimpleNamespace(
        url="https://walmart.com/ip/test/12345", title="Cached product"
    )
    runner = AsyncMock()
    runner.scrape_hypothesis_product.return_value = product
    runner.run_hypothesis.side_effect = [
        RuntimeError("Error code: 503 - upstream unavailable"),
        RunnerResult(result_payload={}),
    ]

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(
            worker_jobs,
            "_create_provider_resolver",
            return_value=_resolver_stub(),
        ),
        patch.object(
            worker_jobs, "_diagnose_provider_failure", AsyncMock(return_value=False)
        ),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result["status"] == "completed"
    runner.scrape_hypothesis_product.assert_awaited_once()
    repository.create_product_snapshot.assert_awaited_once()
    assert runner.run_hypothesis.await_count == 2
    for call in runner.run_hypothesis.await_args_list:
        assert call.kwargs["product"] is product


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "payload", "runner_method", "expected_kwargs"),
    [
        (
            "judgment",
            {
                "a_url": "https://walmart.com/ip/a/111",
                "b_urls": ["https://walmart.com/ip/b/222"],
            },
            "run_judgment",
            ("product_a", "products_b"),
        ),
        (
            "batch",
            {
                "urls": [
                    "https://walmart.com/ip/a/111",
                    "https://walmart.com/ip/b/222",
                ]
            },
            "run_batch",
            ("products",),
        ),
    ],
)
async def test_worker_reuses_scraped_products_for_all_analysis_modes(
    mock_ctx, mode, payload, runner_method, expected_kwargs
):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        mode=mode,
        request_payload={
            **payload,
            "provider": "openai",
            "model": "gpt-5.6",
        },
    )
    products = [
        SimpleNamespace(url="https://walmart.com/ip/a/111", title="A"),
        SimpleNamespace(url="https://walmart.com/ip/b/222", title="B"),
    ]
    runner = AsyncMock()
    runner.scrape_products.return_value = products
    getattr(runner, runner_method).return_value = RunnerResult(result_payload={})

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(
            worker_jobs,
            "_create_provider_resolver",
            return_value=_resolver_stub(),
        ),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result["status"] == "completed"
    runner.scrape_products.assert_awaited_once()
    assert repository.create_product_snapshot.await_count == 2
    run_call = getattr(runner, runner_method).await_args.kwargs
    for key in expected_kwargs:
        assert key in run_call


def test_desktop_worker_provider_resolver_uses_dpapi(tmp_path):
    settings = BackendSettings(
        runtime_mode="desktop",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'desktop.db'}",
        provider_key_file=tmp_path / "provider.key",
    )

    with patch("backend.config.get_backend_settings", return_value=settings):
        resolver = worker_jobs._create_provider_resolver(AsyncMock())

    assert isinstance(resolver._crypto, WindowsDPAPI)


@pytest.mark.asyncio
async def test_worker_claims_job_atomically(mock_ctx):
    job_id = uuid4()
    repository = AsyncMock()
    repository.transition = AsyncMock(return_value=_claimed_job())

    with (
        patch.object(worker_jobs, "SessionFactory") as mock_sf,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=AsyncMock()),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()),
    ):
        mock_sf.return_value.__aenter__.return_value = AsyncMock()
        await worker_jobs.run_analysis_job(mock_ctx, str(job_id))

    repository.transition.assert_awaited_once_with(
        job_id, expected="queued", target="running"
    )


@pytest.mark.asyncio
async def test_worker_skips_already_claimed_job(mock_ctx):
    repository = AsyncMock()
    repository.transition = AsyncMock(return_value=None)

    with (
        patch.object(worker_jobs, "SessionFactory"),
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner"),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()),
    ):
        worker_jobs.SessionFactory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result is None


@pytest.mark.asyncio
async def test_worker_reports_progress_via_redis(mock_ctx):
    job_id = uuid4()
    repository = AsyncMock()
    repository.transition = AsyncMock(return_value=_claimed_job())
    runner_instance = AsyncMock()
    runner_instance.run_hypothesis = AsyncMock(
        return_value=RunnerResult(result_payload={})
    )

    with (
        patch.object(worker_jobs, "SessionFactory"),
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()),
    ):
        worker_jobs.SessionFactory.return_value.__aenter__.return_value = AsyncMock()
        await worker_jobs.run_analysis_job(mock_ctx, str(job_id))

    progress_cb = runner_instance.run_hypothesis.call_args[1].get("report_progress")
    assert progress_cb is not None
    assert callable(progress_cb)
    await progress_cb(35)
    repository.set_progress.assert_awaited_once_with(job_id, 35)
    mock_ctx["redis"].set.assert_awaited_once_with(f"job:{job_id}:progress", 35)


@pytest.mark.asyncio
async def test_worker_invalidates_unroutable_model_after_runtime_404(mock_ctx):
    job_id = uuid4()
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        request_payload={
            "url": "https://walmart.com/ip/test",
            "provider": "custom",
            "model": "claude-opus-4-5-20251101",
        }
    )
    runner_instance = AsyncMock()
    runner_instance.run_hypothesis.side_effect = LLMError(
        "GPT structured output failed: Error code: 404 - "
        "The model 'claude-opus-4-5-20251101' was not found"
    )
    resolver = _resolver_stub()
    resolver.resolve_primary.return_value = SimpleNamespace(
        client=AsyncMock(),
        provider="custom",
        model="claude-opus-4-5-20251101",
    )
    provider_repository = AsyncMock()
    provider_repository.get.return_value = SimpleNamespace(api_protocol="openai")

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=resolver),
        patch(
            "backend.db.provider_repository.ProviderConfigurationRepository",
            return_value=provider_repository,
        ),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(job_id))

    assert result == {"status": "failed", "error_code": "LLM_FAILED"}
    provider_repository.upsert_model_validation.assert_awaited_once()
    persisted = provider_repository.upsert_model_validation.await_args.kwargs
    assert persisted["status"] == "unavailable"
    assert persisted["error_code"] == "PROVIDER_MODEL_INVALID"
    provider_repository.set_model_selected.assert_awaited_once_with(
        "custom", "openai", "claude-opus-4-5-20251101", False
    )


@pytest.mark.asyncio
async def test_worker_runs_one_diagnostic_probe_after_provider_failure(mock_ctx):
    job_id = uuid4()
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        request_payload={
            "url": "https://walmart.com/ip/test",
            "provider": "openai",
            "model": "gpt-test",
        }
    )
    runner_instance = AsyncMock()
    runner_instance.run_hypothesis.side_effect = LLMError(
        "GPT structured output failed: Error code: 503 - upstream unavailable"
    )
    diagnose = AsyncMock()

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()),
        patch.object(worker_jobs, "_diagnose_provider_failure", diagnose),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        await worker_jobs.run_analysis_job(mock_ctx, str(job_id))

    diagnose.assert_awaited_once()
    assert diagnose.await_args.kwargs["provider"] == "openai"
    assert diagnose.await_args.kwargs["model"] == "gpt-test"


@pytest.mark.asyncio
async def test_worker_retries_same_model_once_when_diagnostic_succeeds(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        request_payload={
            "url": "https://walmart.com/ip/test",
            "provider": "openai",
            "model": "gpt-test",
        }
    )
    runner_instance = AsyncMock()
    runner_instance.run_hypothesis.side_effect = [
        LLMError("GPT structured output failed: Error code: 503"),
        RunnerResult(result_payload={"grade": "A"}, artifacts=[]),
    ]
    diagnose = AsyncMock(return_value=True)

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()),
        patch.object(worker_jobs, "_diagnose_provider_failure", diagnose),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {"status": "completed", "error_code": None}
    assert runner_instance.run_hypothesis.await_count == 2
    diagnose.assert_awaited_once()
    assert repository.create_attempt.await_count == 2
    repository.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_rotates_without_probe_after_truncated_json(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        request_payload={
            "url": "https://walmart.com/ip/test",
            "provider": "openai",
            "model": "gpt-5.5-pro",
            "rotation_enabled": True,
            "rotation_candidates": [
                {
                    "provider": "openai",
                    "api_protocol": "openai",
                    "model": "gpt-5.5-pro",
                    "connection_revision": 1,
                },
                {
                    "provider": "openai",
                    "api_protocol": "openai",
                    "model": "gpt-5.6",
                    "connection_revision": 1,
                },
            ],
        }
    )
    runner_instance = AsyncMock()
    runner_instance.run_hypothesis.side_effect = [
        LLMError(
            "LLM structured output parse failed after repair attempt: "
            "invalid JSON: Unterminated string"
        ),
        RunnerResult(result_payload={"grade": "A"}, artifacts=[]),
    ]
    diagnose = AsyncMock(return_value=True)
    resolver = _resolver_stub()
    resolver.resolve_primary.side_effect = [
        SimpleNamespace(client=AsyncMock(), provider="openai", model="gpt-5.5-pro"),
        SimpleNamespace(client=AsyncMock(), provider="openai", model="gpt-5.6"),
    ]

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=resolver),
        patch.object(worker_jobs, "_diagnose_provider_failure", diagnose),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {"status": "completed", "error_code": None}
    assert runner_instance.run_hypothesis.await_count == 2
    diagnose.assert_not_awaited()
    assert repository.create_attempt.await_count == 2
    assert repository.complete.await_args.kwargs["result_payload"]["successful_model"] == "gpt-5.6"


@pytest.mark.asyncio
async def test_worker_does_not_probe_after_result_quality_failure(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        request_payload={
            "url": "https://walmart.com/ip/test",
            "provider": "openai",
            "model": "gpt-test",
            "expected_model_version": "combination_model_v2.1",
        }
    )
    runner_instance = AsyncMock(
        run_hypothesis=AsyncMock(
            return_value=RunnerResult(
                result_payload={
                    "mode": "hypothesis",
                    "model_version": "combination_model_v2.1",
                    "directions_count": 0,
                    "structured_directions": [],
                }
            )
        )
    )
    diagnose = AsyncMock()

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()),
        patch.object(worker_jobs, "_diagnose_provider_failure", diagnose),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    diagnose.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_completes_job_and_persists(mock_ctx):
    repository = AsyncMock()
    repository.transition = AsyncMock(return_value=_claimed_job())
    runner_instance = AsyncMock()
    runner_instance.run_hypothesis = AsyncMock(
        return_value=RunnerResult(result_payload={"grade": "A"}, artifacts=[])
    )

    with (
        patch.object(worker_jobs, "SessionFactory"),
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()),
    ):
        worker_jobs.SessionFactory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result is not None
    repository.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_fails_invalid_v21_result_instead_of_completing(mock_ctx):
    repository = AsyncMock()
    repository.transition = AsyncMock(
        return_value=_claimed_job(
            request_payload={
                "url": "https://walmart.com/ip/test",
                "expected_model_version": "combination_model_v2.1",
            }
        )
    )
    runner_instance = AsyncMock()
    runner_instance.run_hypothesis = AsyncMock(
        return_value=RunnerResult(
            result_payload={
                "mode": "hypothesis",
                "model_version": "combination_model_v2.1",
                "directions_count": 0,
                "structured_directions": [],
            },
            artifacts=[],
        )
    )

    with (
        patch.object(worker_jobs, "SessionFactory"),
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(
            worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()
        ),
    ):
        worker_jobs.SessionFactory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {"status": "failed", "error_code": "RESULT_QUALITY_INVALID"}
    repository.complete.assert_not_awaited()
    repository.fail.assert_awaited_once()
    assert repository.fail.await_args.kwargs["code"] == "RESULT_QUALITY_INVALID"


@pytest.mark.asyncio
async def test_worker_maps_malformed_v21_direction_to_quality_error(mock_ctx):
    repository = AsyncMock()
    repository.transition = AsyncMock(
        return_value=_claimed_job(
            request_payload={
                "url": "https://walmart.com/ip/test",
                "expected_model_version": "combination_model_v2.1",
            }
        )
    )
    runner_instance = AsyncMock()
    runner_instance.run_hypothesis = AsyncMock(
        return_value=RunnerResult(
            result_payload={
                "mode": "hypothesis",
                "model_version": "combination_model_v2.1",
                "directions_count": 1,
                "structured_directions": [None],
            },
            artifacts=[],
        )
    )

    with (
        patch.object(worker_jobs, "SessionFactory"),
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(
            worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()
        ),
    ):
        worker_jobs.SessionFactory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {"status": "failed", "error_code": "RESULT_QUALITY_INVALID"}
    repository.complete.assert_not_awaited()
    assert repository.fail.await_args.kwargs["code"] == "RESULT_QUALITY_INVALID"


@pytest.mark.asyncio
async def test_worker_maps_malformed_v21_batch_wrapper_to_quality_error(mock_ctx):
    repository = AsyncMock()
    repository.transition = AsyncMock(
        return_value=_claimed_job(
            mode="batch",
            request_payload={
                "urls": ["https://walmart.com/ip/test"],
                "expected_model_version": "combination_model_v2.1",
            },
        )
    )
    runner_instance = AsyncMock()
    runner_instance.run_batch = AsyncMock(
        return_value=RunnerResult(
            result_payload={"mode": "batch", "results": None},
            artifacts=[],
        )
    )

    with (
        patch.object(worker_jobs, "SessionFactory"),
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(
            worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()
        ),
    ):
        worker_jobs.SessionFactory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {"status": "failed", "error_code": "RESULT_QUALITY_INVALID"}
    repository.complete.assert_not_awaited()
    assert repository.fail.await_args.kwargs["code"] == "RESULT_QUALITY_INVALID"


@pytest.mark.asyncio
async def test_worker_maps_known_exception_to_stable_code(mock_ctx):
    from app.core.exceptions import ScrapeError

    repository = AsyncMock()
    repository.transition = AsyncMock(return_value=_claimed_job())
    runner_instance = AsyncMock()
    runner_instance.run_hypothesis = AsyncMock(side_effect=ScrapeError("no data"))

    with (
        patch.object(worker_jobs, "SessionFactory"),
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()),
    ):
        worker_jobs.SessionFactory.return_value.__aenter__.return_value = AsyncMock()
        await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    repository.fail.assert_awaited_once()
    call_kwargs = repository.fail.await_args.kwargs
    assert call_kwargs["code"] == "SCRAPE_FAILED"


@pytest.mark.asyncio
async def test_worker_sanitizes_unknown_exception(mock_ctx):
    repository = AsyncMock()
    repository.transition = AsyncMock(return_value=_claimed_job())
    runner_instance = AsyncMock()
    runner_instance.run_hypothesis = AsyncMock(side_effect=RuntimeError("key=sk-abc123"))

    with (
        patch.object(worker_jobs, "SessionFactory"),
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner_instance),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=_resolver_stub()),
    ):
        worker_jobs.SessionFactory.return_value.__aenter__.return_value = AsyncMock()
        await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    repository.fail.assert_awaited_once()
    call_kwargs = repository.fail.await_args.kwargs
    assert call_kwargs["code"] == "INTERNAL_ERROR"
    assert "sk-abc123" not in call_kwargs["message"]
    assert "run_hypothesis" in call_kwargs["message"]
    assert "RuntimeError" in call_kwargs["message"]


@pytest.mark.asyncio
async def test_worker_uses_runtime_provider_resolver_for_custom_model(mock_ctx):
    repository = AsyncMock()
    repository.transition = AsyncMock(
        return_value=_claimed_job(
            request_payload={
                "url": "https://walmart.com/ip/test",
                "provider": "custom",
                "model": "model-x",
            }
        )
    )
    runner = AsyncMock()
    runner.run_hypothesis = AsyncMock(return_value=RunnerResult(result_payload={}))
    resolver = AsyncMock()
    resolver.resolve_primary.return_value = SimpleNamespace(
        client=AsyncMock(),
        provider="custom",
        model="model-x",
    )
    secondary_client = AsyncMock()
    resolver.resolve_secondary_deepseek.return_value = SimpleNamespace(
        client=secondary_client,
        provider="deepseek",
        model="deepseek-reasoner",
    )

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=resolver),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    resolver.resolve_primary.assert_awaited_once_with("custom", "model-x")
    resolver.resolve_secondary_deepseek.assert_awaited_once()
    runner.run_hypothesis.assert_awaited_once()
    kwargs = runner.run_hypothesis.await_args.kwargs
    assert kwargs["provider"] == "custom"
    assert kwargs["provider_model"] == "model-x"
    assert kwargs["llm_secondary"] is secondary_client
    assert kwargs["secondary_provider"] == "deepseek"
    assert kwargs["secondary_provider_model"] == "deepseek-reasoner"


@pytest.mark.asyncio
async def test_worker_rejects_mismatched_contract_before_external_work(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        request_payload={
            "url": "https://walmart.com/ip/test",
            "expected_model_version": "combination_model_v2.0",
            "requested_at_revision": "oldrev1",
        }
    )
    create_browser = patch.object(worker_jobs, "_create_browser")
    create_resolver = patch.object(worker_jobs, "_create_provider_resolver")

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner") as runner,
        create_browser as browser,
        create_resolver as resolver,
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {
        "status": "failed",
        "error_code": "MODEL_CONTRACT_MISMATCH",
    }
    repository.fail.assert_awaited_once()
    assert repository.fail.await_args.kwargs["code"] == "MODEL_CONTRACT_MISMATCH"
    browser.assert_not_called()
    resolver.assert_not_called()
    runner.return_value.run_hypothesis.assert_not_called()


@pytest.mark.asyncio
async def test_worker_rejects_present_empty_contract_before_external_work(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        request_payload={
            "url": "https://walmart.com/ip/test",
            "expected_model_version": "",
            "requested_at_revision": "oldrev1",
        }
    )

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner") as runner,
        patch.object(worker_jobs, "_create_browser") as browser,
        patch.object(worker_jobs, "_create_provider_resolver") as resolver,
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result == {
        "status": "failed",
        "error_code": "MODEL_CONTRACT_MISMATCH",
    }
    repository.fail.assert_awaited_once()
    assert repository.fail.await_args.kwargs["code"] == "MODEL_CONTRACT_MISMATCH"
    browser.assert_not_called()
    resolver.assert_not_called()
    runner.return_value.run_hypothesis.assert_not_called()


@pytest.mark.asyncio
async def test_worker_historical_payload_without_contract_remains_compatible(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job()
    runner = AsyncMock()
    runner.run_hypothesis.return_value = RunnerResult(result_payload={})
    resolver = _resolver_stub()

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=resolver),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        result = await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    assert result["status"] == "completed"
    assert runner.run_hypothesis.await_args.kwargs["expected_model_version"] is None


@pytest.mark.asyncio
async def test_worker_removes_contract_metadata_before_provider_resolution(mock_ctx):
    repository = AsyncMock()
    repository.transition.return_value = _claimed_job(
        request_payload={
            "url": "https://walmart.com/ip/test",
            "provider": "custom",
            "model": "model-x",
            "expected_model_version": "combination_model_v2.1",
            "requested_at_revision": "abc1234",
        }
    )
    runner = AsyncMock()
    runner.run_hypothesis.return_value = RunnerResult(result_payload={})
    resolver = _resolver_stub()
    resolver.resolve_primary.return_value = SimpleNamespace(
        client=AsyncMock(), provider="custom", model="model-x"
    )

    with (
        patch.object(worker_jobs, "SessionFactory") as session_factory,
        patch.object(worker_jobs, "JobRepository", return_value=repository),
        patch.object(worker_jobs, "AnalysisRunner", return_value=runner),
        patch.object(worker_jobs, "_create_browser"),
        patch.object(worker_jobs, "_create_provider_resolver", return_value=resolver),
    ):
        session_factory.return_value.__aenter__.return_value = AsyncMock()
        await worker_jobs.run_analysis_job(mock_ctx, str(uuid4()))

    resolver.resolve_primary.assert_awaited_once_with("custom", "model-x")
    kwargs = runner.run_hypothesis.await_args.kwargs
    assert kwargs["expected_model_version"] == "combination_model_v2.1"
    assert "requested_at_revision" not in kwargs
