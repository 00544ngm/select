from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from app.core.exceptions import BrowserError, ModelContractError
from app.core.logger import logger
from app.core.runtime_contract import EXPECTED_COMBINATION_MODEL_VERSION
from backend.application.analysis_runner import AnalysisRunner, RunnerResult
from backend.application.model_rotation import (
    RotationCandidate,
    RotationExecutionError,
    classify_rotation_failure,
    run_with_rotation,
)
from backend.application.provider_clients import (
    ProviderConnectionTester,
    ProviderModelVerifier,
    ProviderResolutionError,
    classify_provider_error,
)
from backend.application.provider_service import ProviderService
from backend.application.result_quality import (
    validate_batch_payload,
    validate_hypothesis_payload,
)
from backend.db.models import Artifact
from backend.db.repositories import JobRepository
from backend.db.session import SessionFactory
from backend.security.provider_crypto_factory import create_provider_crypto

ERROR_CODE_MAP: dict[str, str] = {
    "ScrapeError": "SCRAPE_FAILED",
    "ScrapeIncompleteError": "SCRAPE_INCOMPLETE",
    "LLMError": "LLM_FAILED",
    "BrowserError": "BROWSER_FAILED",
    "BrowserTargetClosedError": "BROWSER_TARGET_CLOSED",
    "UnsupportedPlatformError": "INVALID_URL",
}

# 单任务可执行时限（秒）。ARQ job_timeout 作为外层兜底；内层按任务首选的
# provider/model 施加更精确的执行上限，使放宽只作用于 Maike 中转的 gpt 通道。
_STANDARD_JOB_DEADLINE_SECONDS = 600.0
_MAIKE_GPT_JOB_DEADLINE_SECONDS = 1000.0


def _resolve_job_deadline(provider: str | None, model: str | None) -> float:
    """按任务首选 provider/model 选择可执行上限（秒）。

    当前 provider slug "custom" 对应 Maike 中转的 OpenAI 兼容通道
    （https://maike-ai.top/v1）。该通道的真实完整请求很慢（约 5 分钟）且首试
    常被上游判为不可用，需要在受控自动重试后再给出一次约 5 分钟的窗口；因此该
    组合放宽到 1000 秒。OpenAI/DeepSeek/Anthropic 及其它模型维持 600 秒不变。
    """
    if provider == "custom" and str(model or "").strip().lower().startswith("gpt-"):
        return _MAIKE_GPT_JOB_DEADLINE_SECONDS
    return _STANDARD_JOB_DEADLINE_SECONDS


async def run_analysis_job(ctx: dict, job_id: str) -> dict | None:
    job_uuid = UUID(job_id)

    async with SessionFactory() as session:
        repository = JobRepository(session)
        claimed = await repository.transition(
            job_uuid, expected="queued", target="running"
        )
        if claimed is None:
            return None

        runner = AnalysisRunner()
        runner_result: RunnerResult | None = None
        error_code: str | None = None
        error_message: str | None = None
        stage = "prepare"
        provider: str | None = None
        model: str | None = None
        analysis_browser = None
        # ApiGroup scope for this job (None = global default set). Set from the
        # payload below; defaulted here so failure paths that fire before the
        # payload is fully read (e.g. contract mismatch) still resolve cleanly.
        job_scope: str | None = None

        try:
            job_data = dict(claimed.request_payload)
            mode = claimed.mode
            expected_model_version = job_data.pop("expected_model_version", None)
            job_data.pop("requested_at_revision", None)
            if (
                expected_model_version is not None
                and expected_model_version != EXPECTED_COMBINATION_MODEL_VERSION
            ):
                raise ModelContractError(
                    expected=expected_model_version,
                    actual=EXPECTED_COMBINATION_MODEL_VERSION,
                )

            async def report_progress(pct: int) -> None:
                await repository.set_progress(job_uuid, pct)
                await _set_progress(ctx, job_uuid, pct)

            async def report_walmart_verification(waiting: bool) -> None:
                await repository.set_runtime_notice(
                    job_uuid,
                    code="WALMART_CAPTCHA_REQUIRED" if waiting else None,
                    message=(
                        "已打开 Walmart 验证窗口，请完成人工验证；"
                        "验证通过后任务会自动继续，模型尚未调用。"
                        if waiting
                        else None
                    ),
                )

            requested_model = job_data.pop("model", None)
            requested_provider = job_data.pop("provider", None) or "openai"
            # The ApiGroup whose API settings this job must run under (None =
            # the global default set). Persisted on the payload at submit time
            # so the worker resolves the same scope regardless of who retries.
            job_scope = job_data.pop("api_group_id", None)
            rotation_enabled = bool(job_data.pop("rotation_enabled", False))
            raw_candidates = job_data.pop("rotation_candidates", None)
            candidates = [
                RotationCandidate(
                    provider=str(item.get("provider") or requested_provider),
                    api_protocol=str(item.get("api_protocol") or "openai"),
                    model=str(item.get("model") or requested_model or ""),
                    connection_revision=int(item.get("connection_revision") or 1),
                )
                for item in (raw_candidates or [])
            ]
            if not candidates:
                candidates = [
                    RotationCandidate(
                        provider=requested_provider,
                        api_protocol="openai",
                        model=str(requested_model or ""),
                    )
                ]

            attempt_ordinal = 0
            diagnosed_candidates: set[tuple[str, str, str, int]] = set()
            stage = "scrape_product"
            scrape_browser = _create_browser()
            if mode == "hypothesis":
                scraped_products = [
                    await runner.scrape_hypothesis_product(
                        url=job_data["url"],
                        browser=scrape_browser,
                        verification_status=report_walmart_verification,
                    )
                ]
            elif mode == "judgment":
                scrape_urls = [job_data["a_url"], *job_data.get("b_urls", [])]
                scraped_products = await runner.scrape_products(
                    scrape_urls,
                    browser=scrape_browser,
                    verification_status=report_walmart_verification,
                )
            else:
                scrape_urls = list(job_data.get("urls", []))
                scraped_products = await runner.scrape_products(
                    scrape_urls,
                    browser=scrape_browser,
                    verification_status=report_walmart_verification,
                )
            for position, product_snapshot in enumerate(scraped_products):
                role = (
                    "main"
                    if mode != "judgment" or position == 0
                    else "auxiliary"
                )
                await repository.create_product_snapshot(
                    job_uuid,
                    product_snapshot,
                    role=role,
                    position=position,
                )

            stage = "create_browser"
            analysis_browser = _create_browser()
            await runner.start_browser(analysis_browser)

            async def run_one(candidate: RotationCandidate) -> RunnerResult:
                nonlocal attempt_ordinal, model, provider, stage
                provider = candidate.provider
                model = candidate.model or None
                attempt_ordinal += 1
                attempt = await repository.create_attempt(
                    job_uuid,
                    ordinal=attempt_ordinal,
                    provider=candidate.provider,
                    api_protocol=candidate.api_protocol,
                    model=candidate.model,
                )
                try:
                    resolver = _create_provider_resolver(session, group_id=job_scope)
                    if rotation_enabled:
                        provider_repository = getattr(resolver, "_repository", None)
                        if provider_repository is not None:
                            configured = await provider_repository.get(candidate.provider)
                            current_revision = getattr(configured, "validation_revision", None)
                            if (
                                isinstance(current_revision, int)
                                and current_revision != candidate.connection_revision
                            ):
                                raise ProviderResolutionError(
                                    code="PROVIDER_CONNECTION_REVISION_CHANGED",
                                    message="模型连接配置已变化，请重新提交任务",
                                    retryable=False,
                                )
                    stage = "resolve_primary_provider"
                    resolved = await resolver.resolve_primary(
                        candidate.provider,
                        candidate.model or None,
                    )
                    llm = resolved.client
                    stage = "resolve_optional_secondary"
                    resolved_secondary = await resolver.resolve_secondary_deepseek()
                    llm_secondary = (
                        resolved_secondary.client
                        if resolved_secondary is not None
                        else None
                    )
                    secondary_provider = (
                        resolved_secondary.provider
                        if resolved_secondary is not None
                        else ""
                    )
                    secondary_provider_model = (
                        resolved_secondary.model
                        if resolved_secondary is not None
                        else ""
                    )

                    if mode == "hypothesis":
                        stage = "run_hypothesis"
                        result = await runner.run_hypothesis(
                            url=job_data["url"],
                            browser=analysis_browser,
                            llm=llm,
                            llm_secondary=llm_secondary,
                            expected_model_version=expected_model_version,
                            provider=resolved.provider,
                            provider_model=resolved.model,
                            secondary_provider=secondary_provider,
                            secondary_provider_model=secondary_provider_model,
                            product=scraped_products[0],
                            browser_started=True,
                            report_progress=report_progress,
                        )
                    elif mode == "judgment":
                        stage = "run_judgment"
                        result = await runner.run_judgment(
                            a_url=job_data["a_url"],
                            b_urls=job_data.get("b_urls", []),
                            browser=analysis_browser,
                            llm=llm,
                            llm_secondary=llm_secondary,
                            product_a=scraped_products[0],
                            products_b=scraped_products[1:],
                            browser_started=True,
                            report_progress=report_progress,
                        )
                    else:
                        stage = "run_batch"
                        result = await runner.run_batch(
                            urls=job_data.get("urls", []),
                            browser=analysis_browser,
                            llm=llm,
                            llm_secondary=llm_secondary,
                            expected_model_version=expected_model_version,
                            provider=resolved.provider,
                            provider_model=resolved.model,
                            secondary_provider=secondary_provider,
                            secondary_provider_model=secondary_provider_model,
                            products=scraped_products,
                            browser_started=True,
                            report_progress=report_progress,
                        )
                    if result is None:
                        stage = "parse"
                        raise ValueError("empty response")
                    if mode in {"hypothesis", "batch"}:
                        stage = "schema"
                        if mode == "batch":
                            validate_batch_payload(
                                result.result_payload,
                                expected_model_version=expected_model_version,
                            )
                        else:
                            validate_hypothesis_payload(
                                result.result_payload,
                                expected_model_version=expected_model_version,
                            )
                    await repository.finish_attempt(
                        attempt.id,
                        status="succeeded",
                        stage="complete",
                    )
                    return result
                except Exception as error:
                    if isinstance(error, BrowserError):
                        await repository.delete_attempt(attempt.id)
                        raise
                    try:
                        error._rotation_stage = stage
                    except (AttributeError, TypeError):  # pragma: no cover - unusual immutable error
                        logger.debug("Unable to attach rotation stage to %s", type(error).__name__)
                    failure = classify_rotation_failure(error, stage=stage)
                    candidate_key = (
                        candidate.provider,
                        candidate.api_protocol,
                        candidate.model,
                        candidate.connection_revision,
                    )
                    should_diagnose = (
                        candidate_key not in diagnosed_candidates
                        and _should_diagnose_provider_failure(error, failure.code)
                    )
                    await repository.finish_attempt(
                        attempt.id,
                        status="failed",
                        stage=failure.stage,
                        error_code=failure.code,
                        error_message=failure.message,
                    )
                    if should_diagnose:
                        diagnosed_candidates.add(candidate_key)
                        try:
                            diagnostic_succeeded = await _diagnose_provider_failure(
                                session,
                                provider=candidate.provider,
                                model=candidate.model,
                                group_id=job_scope,
                            )
                        except Exception as diagnostic_error:  # noqa: BLE001 - original task error wins
                            logger.warning(
                                "Provider diagnostic failed provider={} model={} error_type={}",
                                candidate.provider,
                                candidate.model,
                                type(diagnostic_error).__name__,
                            )
                        else:
                            if diagnostic_succeeded:
                                return await run_one(candidate)
                    raise

            deadline_s = _resolve_job_deadline(
                requested_provider, requested_model
            )
            async with asyncio.timeout(deadline_s):
                rotation = await run_with_rotation(
                    candidates,
                    run_one,
                    enabled=rotation_enabled,
                )
                await runner.stop_browser(analysis_browser)
                analysis_browser = None
                runner_result = rotation.result
                raw_result_payload = getattr(runner_result, "result_payload", None)
                final_payload = (
                    dict(raw_result_payload)
                    if isinstance(raw_result_payload, dict)
                    else {}
                )
                final_payload.setdefault(
                    "provider", rotation.successful_candidate.provider
                )
                final_payload.setdefault(
                    "provider_model", rotation.successful_candidate.model
                )
                final_payload["successful_model"] = rotation.successful_candidate.model
                if rotation_enabled:
                    final_payload["rotation_enabled"] = True
                    final_payload["rotation_failures"] = [
                        {"code": failure.code, "stage": failure.stage}
                        for failure in rotation.failures
                    ]
                await repository.complete(
                    job_uuid,
                    result_payload=final_payload,
                )
                for info in runner_result.artifacts:
                    session.add(
                        Artifact(
                            job_id=job_uuid,
                            kind=info.kind,
                            path=info.path,
                            size=info.size,
                            checksum=info.checksum,
                        )
                    )
                await session.commit()

        except BaseException as exc:  # noqa: BLE001 - persist every worker termination
            if analysis_browser is not None:
                await runner.stop_browser(analysis_browser)
            logger.exception(
                "Analysis job failed at stage={} exception_type={}",
                stage,
                type(exc).__name__,
            )
            error_code, error_message = _classify_error(exc, stage=stage)
            await _invalidate_unroutable_provider_model(
                session,
                provider=provider,
                model=model,
                error=exc,
                group_id=job_scope,
            )
            await repository.fail(job_uuid, code=error_code, message=error_message)

        return {
            "status": "completed" if error_code is None else "failed",
            "error_code": error_code,
        }


async def _set_progress(ctx: dict, job_id: UUID, pct: int) -> None:
    redis = ctx.get("redis")
    if redis is not None:
        await redis.set(f"job:{job_id}:progress", pct)


def _create_browser():
    from app.infrastructure.browser import PlaywrightBrowserManager

    return PlaywrightBrowserManager()


def _provider_repository(session, group_id=None):
    from backend.db.provider_repository import (
        GroupProviderRepository,
        ProviderConfigurationRepository,
    )

    if group_id:
        return GroupProviderRepository(session, api_group_id=UUID(group_id))
    return ProviderConfigurationRepository(session)


def _create_provider_resolver(session, group_id=None):
    from backend.application.provider_clients import ProviderClientResolver
    from backend.config import get_backend_settings

    settings = get_backend_settings()
    return ProviderClientResolver(
        repository=_provider_repository(session, group_id),
        crypto=create_provider_crypto(settings),
        group_scoped=bool(group_id),
    )


def _should_diagnose_provider_failure(error: BaseException, failure_code: str) -> bool:
    if failure_code in {
        "MODEL_TIMEOUT",
        "MODEL_RATE_LIMITED",
        "MODEL_UPSTREAM_UNAVAILABLE",
        "MODEL_EMPTY_RESPONSE",
        "MODEL_SCHEMA_INVALID",
        "PROVIDER_AUTH_FAILED",
        "PROVIDER_MODEL_INVALID",
        "PROVIDER_MODEL_ROUTE_UNAVAILABLE",
    }:
        return True
    chain: list[str] = []
    current: BaseException | None = error
    status_code = None
    for _ in range(6):
        if current is None:
            break
        chain.append(str(current))
        candidate_status = getattr(current, "status_code", None)
        if status_code is None and isinstance(candidate_status, int):
            status_code = candidate_status
        current = current.__cause__
    classified = classify_provider_error(" ".join(chain), status_code=status_code)
    normalized = " ".join(chain).lower()
    return classified.code != "PROVIDER_UNAVAILABLE" or any(
        marker in normalized
        for marker in (
            "timeout",
            "timed out",
            "error 500",
            "error 502",
            "error 503",
            "error code: 500",
            "error code: 502",
            "error code: 503",
        )
    )


async def _diagnose_provider_failure(
    session,
    *,
    provider: str,
    model: str,
    group_id=None,
) -> bool:
    from backend.config import get_backend_settings

    service = ProviderService(
        repository=_provider_repository(session, group_id),
        crypto=create_provider_crypto(get_backend_settings()),
        connection_test=ProviderConnectionTester(),
        model_verifier=ProviderModelVerifier(),
    )
    result = await service.verify_model(
        provider,
        model,
        set_default=False,
        is_automatic=True,
    )
    return result.test_status == "verified"


async def _invalidate_unroutable_provider_model(
    session,
    *,
    provider: str | None,
    model: str | None,
    error: BaseException,
    group_id=None,
) -> None:
    if not provider or not model:
        return
    chain: list[str] = []
    current: BaseException | None = error
    status_code = None
    for _ in range(6):
        if current is None:
            break
        chain.append(str(current))
        candidate_status = getattr(current, "status_code", None)
        if status_code is None and isinstance(candidate_status, int):
            status_code = candidate_status
        current = current.__cause__
    classified = classify_provider_error(" ".join(chain), status_code=status_code)
    if classified.code not in {
        "PROVIDER_MODEL_INVALID",
        "PROVIDER_MODEL_ROUTE_UNAVAILABLE",
    }:
        return

    repository = _provider_repository(session, group_id)
    record = await repository.get(provider)
    if record is None:
        return
    await repository.upsert_model_validation(
        provider_slug=provider,
        api_protocol=record.api_protocol,
        model=model,
        status="unavailable",
        error_code=classified.code,
        message=classified.message,
        tested_at=datetime.now(timezone.utc),
    )
    await repository.set_model_selected(
        provider, record.api_protocol, model, False
    )


def _classify_error(exc: Exception, *, stage: str = "unknown") -> tuple[str, str]:
    if isinstance(exc, RotationExecutionError):
        cause = exc.__cause__
        if cause is not None and not exc.failure.retryable:
            return _classify_error(cause, stage=exc.failure.stage)
        if exc.failure.code == "MODEL_RESULT_QUALITY_INVALID":
            return "RESULT_QUALITY_INVALID", "模型报告未通过质量校验"
        return exc.failure.code, exc.failure.message
    if hasattr(exc, "code") and hasattr(exc, "message"):
        return str(exc.code), str(exc.message)
    exc_name = type(exc).__name__
    code = ERROR_CODE_MAP.get(exc_name, "INTERNAL_ERROR")
    if code != "INTERNAL_ERROR":
        message = str(exc)
    else:
        stage_labels = {
            "prepare": "准备任务",
            "create_browser": "创建浏览器",
            "resolve_primary_provider": "读取主模型配置",
            "resolve_optional_secondary": "读取辅助模型配置",
            "run_hypothesis": "模型分析",
            "run_judgment": "对比审判",
            "run_batch": "批量分析",
        }
        label = stage_labels.get(stage, "执行任务")
        message = (
            f"任务在“{label}”阶段失败（{exc_name}），"
            f"请打开日志目录查看技术详情。阶段：{stage}"
        )
    return code, message


async def run_cross_review(ctx: dict, job_id: str) -> dict | None:
    """Run cross-review on a completed dual-model job."""
    from uuid import UUID as _UUID

    job_uuid = _UUID(job_id)

    try:
        async with SessionFactory() as session:
            repository = JobRepository(session)
            job = await repository.get(job_uuid)
            if job is None or job.status != "completed":
                return {"status": "skipped", "reason": "job not found or not completed"}

            payload = dict(job.result_payload or {})
            models = payload.get("models")
            if not models or len(models) < 2:
                return {"status": "skipped", "reason": "not a dual-model job"}

            product_summary = payload.get("product_summary")
            if not product_summary:
                return {"status": "skipped", "reason": "no product_summary in payload"}

            mode = payload.get("mode", "hypothesis")
            review_state = dict(payload.get("cross_review") or {})
            reviewers = review_state.get("reviewers") or []
            if len(reviewers) != 2:
                return {"status": "skipped", "reason": "no selected reviewers"}
            review_state["status"] = "running"
            payload["cross_review"] = review_state
            await repository.update_result_payload(job_uuid, result_payload=payload)
            output_values = list(models.values())[:2]

            runner = AnalysisRunner()
            request_payload = job.request_payload if isinstance(job.request_payload, dict) else {}
            resolver = _create_provider_resolver(
                session, group_id=request_payload.get("api_group_id")
            )
            resolved_a = await resolver.resolve_primary(reviewers[0]["provider"], reviewers[0]["model"])
            resolved_b = await resolver.resolve_primary(reviewers[1]["provider"], reviewers[1]["model"])
            cross_review = await runner.run_cross_review(
                llm=resolved_a.client,
                llm_secondary=resolved_b.client,
                product_summary=product_summary,
                reviewer_a=reviewers[0],
                reviewer_b=reviewers[1],
                output_a=dict(output_values[0]),
                output_b=dict(output_values[1]),
                mode=mode,
            )
            payload["cross_review"] = {"status": "completed", "reviewers": reviewers, "results": cross_review["results"]}
            await repository.update_result_payload(job_uuid, result_payload=payload)

    except Exception as exc:  # noqa: BLE001 - cross-review worker boundary
        safe_message = str(exc).replace("api_key", "credential")[:240]
        async with SessionFactory() as error_session:
            error_repo = JobRepository(error_session)
            job = await error_repo.get(job_uuid)
            if job is not None:
                failed_payload = dict(job.result_payload or {})
                failed_payload["cross_review"] = {**dict(failed_payload.get("cross_review") or {}), "status": "failed", "error": safe_message}
                await error_repo.update_result_payload(job_uuid, result_payload=failed_payload)
        return {"status": "failed", "error": safe_message}

    return {"status": "completed", "cross_review": True}
