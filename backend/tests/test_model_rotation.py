from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import pytest

from backend.application.model_rotation import (
    RotationCandidate,
    RotationExhaustedError,
    RotationTerminalError,
    classify_rotation_failure,
    run_with_rotation,
)
from backend.application.provider_clients import ProviderConnectionError
from backend.application.result_quality import ResultQualityError


class RateLimitedError(RuntimeError):
    status_code = 429


class UpstreamError(RuntimeError):
    status_code = 503


@pytest.mark.parametrize(
    ("error", "stage", "code"),
    [
        (asyncio.TimeoutError(), "request", "MODEL_TIMEOUT"),
        (RateLimitedError(), "request", "MODEL_RATE_LIMITED"),
        (UpstreamError(), "request", "MODEL_UPSTREAM_UNAVAILABLE"),
        (RuntimeError("Error code: 503 - upstream unavailable"), "run_hypothesis", "MODEL_UPSTREAM_UNAVAILABLE"),
        (
            RuntimeError(
                "LLM structured output parse failed after repair attempt: "
                "GPT structured output failed: invalid JSON: Unterminated string"
            ),
            "run_hypothesis",
            "MODEL_INVALID_JSON",
        ),
        (ValueError("empty response"), "parse", "MODEL_EMPTY_RESPONSE"),
        (json.JSONDecodeError("invalid", "{", 1), "parse", "MODEL_INVALID_JSON"),
        (ValueError("schema validation failed"), "schema", "MODEL_SCHEMA_INVALID"),
        (ResultQualityError("quality gate"), "quality", "MODEL_RESULT_QUALITY_INVALID"),
    ],
)
def test_classify_retryable_model_failures(error, stage, code):
    failure = classify_rotation_failure(error, stage=stage)

    assert failure.retryable is True
    assert failure.code == code
    assert failure.stage == stage


def test_classify_auth_failure_as_terminal():
    failure = classify_rotation_failure(
        ProviderConnectionError(
            code="PROVIDER_AUTH_FAILED",
            message="API Key 无效",
            retryable=False,
        ),
        stage="request",
    )

    assert failure.retryable is False
    assert failure.code == "PROVIDER_AUTH_FAILED"


@pytest.mark.parametrize(
    "code",
    [
        "PROVIDER_PERMISSION_DENIED",
        "PROVIDER_MODEL_INVALID",
        "PROVIDER_PROTOCOL_MISMATCH",
        "PROVIDER_STRUCTURED_OUTPUT_UNSUPPORTED",
        "PROVIDER_REQUEST_TOO_LARGE",
    ],
)
def test_classify_anthropic_configuration_failures_with_stable_code(code):
    failure = classify_rotation_failure(
        ProviderConnectionError(
            code=code,
            message="safe provider failure",
            retryable=False,
        ),
        stage="request",
    )

    assert failure.retryable is False
    assert failure.code == code


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("PROVIDER_CONNECTION_FAILED", "MODEL_UPSTREAM_UNAVAILABLE"),
        ("PROVIDER_EMPTY_RESPONSE", "MODEL_UPSTREAM_UNAVAILABLE"),
        ("MODEL_INVALID_JSON", "MODEL_INVALID_JSON"),
    ],
)
def test_classify_anthropic_retryable_failures(code, expected):
    failure = classify_rotation_failure(
        ProviderConnectionError(
            code=code,
            message="safe provider failure",
            retryable=True,
        ),
        stage="request",
    )

    assert failure.retryable is True
    assert failure.code == expected


@dataclass
class FakeReport:
    result_status: str


@pytest.mark.asyncio
async def test_rotation_tries_next_model_only_after_technical_failure():
    calls: list[str] = []
    candidates = [
        RotationCandidate(provider="openai", api_protocol="openai", model="gpt-5.6"),
        RotationCandidate(provider="openai", api_protocol="openai", model="gpt-5.5"),
    ]

    async def run_one(candidate: RotationCandidate) -> FakeReport:
        calls.append(candidate.model)
        if candidate.model == "gpt-5.6":
            raise asyncio.TimeoutError()
        return FakeReport("completed_with_qualified_candidates")

    result = await run_with_rotation(candidates, run_one)

    assert calls == ["gpt-5.6", "gpt-5.5"]
    assert result.successful_candidate.model == "gpt-5.5"
    assert result.result.result_status == "completed_with_qualified_candidates"
    assert [failure.code for failure in result.failures] == ["MODEL_TIMEOUT"]


@pytest.mark.asyncio
async def test_rotation_tries_next_model_after_truncated_structured_output():
    calls: list[str] = []
    candidates = [
        RotationCandidate(provider="openai", api_protocol="openai", model="gpt-5.5-pro"),
        RotationCandidate(provider="openai", api_protocol="openai", model="gpt-5.6"),
    ]

    async def run_one(candidate: RotationCandidate) -> FakeReport:
        calls.append(candidate.model)
        if candidate.model == "gpt-5.5-pro":
            raise RuntimeError(
                "LLM structured output parse failed after repair attempt: "
                "GPT structured output failed: invalid JSON: Unterminated string"
            )
        return FakeReport("completed_with_qualified_candidates")

    result = await run_with_rotation(candidates, run_one)

    assert calls == ["gpt-5.5-pro", "gpt-5.6"]
    assert result.successful_candidate.model == "gpt-5.6"
    assert [failure.code for failure in result.failures] == ["MODEL_INVALID_JSON"]


@pytest.mark.asyncio
async def test_rotation_does_not_switch_after_no_qualified_candidates():
    calls: list[str] = []
    candidates = [
        RotationCandidate(provider="openai", api_protocol="openai", model="gpt-5.6"),
        RotationCandidate(provider="openai", api_protocol="openai", model="gpt-5.5"),
    ]

    async def run_one(candidate: RotationCandidate) -> FakeReport:
        calls.append(candidate.model)
        return FakeReport("completed_no_qualified_candidates")

    result = await run_with_rotation(candidates, run_one)

    assert calls == ["gpt-5.6"]
    assert result.result.result_status == "completed_no_qualified_candidates"


@pytest.mark.asyncio
async def test_disabled_rotation_uses_only_requested_model():
    calls: list[str] = []
    candidates = [
        RotationCandidate(provider="openai", api_protocol="openai", model="gpt-5.6"),
        RotationCandidate(provider="openai", api_protocol="openai", model="gpt-5.5"),
    ]

    async def run_one(candidate: RotationCandidate) -> FakeReport:
        calls.append(candidate.model)
        raise asyncio.TimeoutError()

    with pytest.raises(RotationTerminalError) as error:
        await run_with_rotation(candidates, run_one, enabled=False)

    assert calls == ["gpt-5.6"]
    assert error.value.failure.code == "MODEL_TIMEOUT"


@pytest.mark.asyncio
async def test_all_technical_failures_return_exhausted_error():
    candidates = [
        RotationCandidate(provider="openai", api_protocol="openai", model="gpt-5.6"),
        RotationCandidate(provider="openai", api_protocol="openai", model="gpt-5.5"),
    ]

    async def run_one(candidate: RotationCandidate) -> FakeReport:
        raise asyncio.TimeoutError()

    with pytest.raises(RotationExhaustedError) as error:
        await run_with_rotation(candidates, run_one)

    assert [failure.code for failure in error.value.failures] == [
        "MODEL_TIMEOUT",
        "MODEL_TIMEOUT",
    ]
