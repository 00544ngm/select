from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.core.exceptions import BrowserError, BrowserTargetClosedError, ScrapeError
from backend.application.result_quality import ResultQualityError


@dataclass(frozen=True)
class RotationCandidate:
    provider: str
    api_protocol: str
    model: str
    connection_revision: int = 1


@dataclass(frozen=True)
class RotationFailure:
    code: str
    stage: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class RotationResult:
    result: Any
    successful_candidate: RotationCandidate
    failures: list[RotationFailure]


class RotationExecutionError(RuntimeError):
    def __init__(
        self,
        failure: RotationFailure,
        failures: list[RotationFailure],
    ) -> None:
        super().__init__(failure.message)
        self.failure = failure
        self.failures = failures


class RotationTerminalError(RotationExecutionError):
    pass


class RotationExhaustedError(RotationExecutionError):
    def __init__(self, failures: list[RotationFailure]) -> None:
        failure = failures[-1]
        super().__init__(failure, failures)


def _safe_error_text(error: BaseException) -> str:
    return type(error).__name__


def _provider_error(error: BaseException) -> RotationFailure | None:
    code = getattr(error, "code", None)
    message = getattr(error, "message", None)
    retryable = getattr(error, "retryable", None)
    if not isinstance(code, str) or not isinstance(retryable, bool):
        return None
    if code == "PROVIDER_MODEL_TASK_TIMEOUT":
        return RotationFailure("MODEL_TIMEOUT", "request", "模型请求超时", True)
    if code in {
        "PROVIDER_AUTH_FAILED",
        "PROVIDER_PERMISSION_DENIED",
        "PROVIDER_MODEL_INVALID",
        "PROVIDER_MODEL_ROUTE_UNAVAILABLE",
        "PROVIDER_PROTOCOL_MISMATCH",
        "PROVIDER_STRUCTURED_OUTPUT_UNSUPPORTED",
        "PROVIDER_REQUEST_TOO_LARGE",
    }:
        return RotationFailure(code, "request", str(message or code), False)
    if code == "MODEL_INVALID_JSON":
        return RotationFailure(
            "MODEL_INVALID_JSON",
            "request",
            "模型返回的结构化 JSON 不完整或无效",
            True,
        )
    if code == "PROVIDER_RATE_LIMITED":
        return RotationFailure("MODEL_RATE_LIMITED", "request", "模型请求受到限流", True)
    if code == "PROVIDER_UPSTREAM_UNAVAILABLE":
        return RotationFailure(
            "MODEL_UPSTREAM_UNAVAILABLE", "request", "模型上游暂时不可用", True
        )
    if retryable and code.startswith("PROVIDER_"):
        return RotationFailure(
            "MODEL_UPSTREAM_UNAVAILABLE", "request", "模型请求暂时不可用", True
        )
    return None


def classify_rotation_failure(
    error: BaseException, *, stage: str
) -> RotationFailure:
    if isinstance(error, BrowserTargetClosedError):
        return RotationFailure(
            "BROWSER_TARGET_CLOSED", "scrape", str(error), False
        )
    if isinstance(error, (BrowserError, ScrapeError)):
        return RotationFailure("BROWSER_FAILED", "scrape", str(error), False)
    if isinstance(error, ResultQualityError):
        return RotationFailure(
            "MODEL_RESULT_QUALITY_INVALID", stage, "模型报告未通过质量校验", True
        )
    provider_failure = _provider_error(error)
    if provider_failure is not None:
        return RotationFailure(
            provider_failure.code,
            stage,
            provider_failure.message,
            provider_failure.retryable,
        )

    status_code = getattr(error, "status_code", None)
    chain_text: list[str] = []
    current: BaseException | None = error
    for _ in range(6):
        if current is None:
            break
        chain_text.append(str(current))
        if status_code is None:
            candidate_status = getattr(current, "status_code", None)
            if isinstance(candidate_status, int):
                status_code = candidate_status
        current = current.__cause__
    normalized_chain = " ".join(chain_text).lower()
    if "not found" in normalized_chain or "model_not_found" in normalized_chain:
        return RotationFailure("PROVIDER_MODEL_INVALID", stage, "当前模型不存在或暂不可用", False)
    text = f"{_safe_error_text(error)} {normalized_chain}"
    if any(
        marker in normalized_chain
        for marker in (
            "invalid json",
            "unterminated string",
            "response truncated",
        )
    ):
        return RotationFailure(
            "MODEL_INVALID_JSON", stage, "模型返回的结构化 JSON 不完整或无效", True
        )
    if isinstance(error, asyncio.TimeoutError) or "timeout" in text:
        return RotationFailure("MODEL_TIMEOUT", stage, "模型请求超时", True)
    if status_code == 429 or "rate" in text and "limit" in text:
        return RotationFailure("MODEL_RATE_LIMITED", stage, "模型请求受到限流", True)
    if (
        isinstance(status_code, int) and status_code >= 500
    ) or any(
        marker in normalized_chain
        for marker in (
            "error 500",
            "error 502",
            "error 503",
            "error code: 500",
            "error code: 502",
            "error code: 503",
        )
    ):
        return RotationFailure(
            "MODEL_UPSTREAM_UNAVAILABLE", stage, "模型上游暂时不可用", True
        )

    if stage == "parse":
        if isinstance(error, json.JSONDecodeError):
            return RotationFailure("MODEL_INVALID_JSON", stage, "模型返回的 JSON 无效", True)
        if isinstance(error, (TypeError, ValueError)):
            return RotationFailure("MODEL_EMPTY_RESPONSE", stage, "模型返回为空", True)
    if stage == "schema":
        return RotationFailure("MODEL_SCHEMA_INVALID", stage, "模型报告结构无效", True)
    if stage == "quality":
        return RotationFailure(
            "MODEL_RESULT_QUALITY_INVALID", stage, "模型报告未通过质量校验", True
        )
    if stage in {"request", "response"}:
        return RotationFailure(
            "MODEL_UPSTREAM_UNAVAILABLE", stage, "模型请求暂时不可用", True
        )
    return RotationFailure("MODEL_EXECUTION_FAILED", stage, "模型执行失败", False)


async def run_with_rotation(
    candidates: list[RotationCandidate],
    run_one: Callable[[RotationCandidate], Awaitable[Any]],
    *,
    enabled: bool = True,
) -> RotationResult:
    if not candidates:
        raise ValueError("at least one rotation candidate is required")

    failures: list[RotationFailure] = []
    ordered = candidates if enabled else candidates[:1]
    for index, candidate in enumerate(ordered):
        try:
            result = await run_one(candidate)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Worker attempts attach the stage before re-raising so the
            # rotation policy does not collapse scrape/provider failures into
            # a generic model-request failure.
            stage = getattr(
                error,
                "_rotation_stage",
                getattr(error, "stage", "request"),
            )
            failure = classify_rotation_failure(error, stage=stage)
            failures.append(failure)
            if not failure.retryable:
                raise RotationTerminalError(failure, failures) from error
            if not enabled:
                raise RotationTerminalError(failure, failures) from error
            if index == len(ordered) - 1:
                raise RotationExhaustedError(failures) from error
            continue
        return RotationResult(
            result=result,
            successful_candidate=candidate,
            failures=failures,
        )

    raise RotationExhaustedError(failures)


__all__ = [
    "RotationCandidate",
    "RotationExecutionError",
    "RotationExhaustedError",
    "RotationFailure",
    "RotationResult",
    "RotationTerminalError",
    "classify_rotation_failure",
    "run_with_rotation",
]
