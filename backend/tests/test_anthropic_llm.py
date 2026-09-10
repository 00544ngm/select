from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import anthropic
import httpx
import pytest

from app.core.exceptions import LLMError
from app.infrastructure.llm import AnthropicLLMClient
from app.infrastructure.llm import anthropic_client as anthropic_module


def response_with_text(*parts: str):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=part) for part in parts]
    )


class AsyncMessageStream:
    def __init__(self, response):
        self.response = response
        self.get_final_message = AsyncMock(return_value=response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://api.example.com", "https://api.example.com"),
        ("https://api.example.com/", "https://api.example.com"),
        ("https://api.example.com/v1", "https://api.example.com"),
        ("https://api.example.com/v1/messages", "https://api.example.com"),
        (
            "https://api.example.com/gateway/v1/messages?trace=1#result",
            "https://api.example.com/gateway",
        ),
    ],
)
def test_normalize_anthropic_base_url(raw, expected):
    assert anthropic_module.normalize_anthropic_base_url(raw) == expected


@pytest.mark.parametrize("raw", ["api.example.com", "ftp://api.example.com"])
def test_normalize_anthropic_base_url_rejects_invalid_scheme(raw):
    with pytest.raises(ValueError, match="http"):
        anthropic_module.normalize_anthropic_base_url(raw)


@pytest.mark.asyncio
async def test_anthropic_chat_separates_system_messages_and_joins_text_blocks():
    create = AsyncMock(return_value=response_with_text("part one", "part two"))
    factory = AsyncMock(
        return_value=SimpleNamespace(messages=SimpleNamespace(create=create))
    )
    client = AnthropicLLMClient(
        api_key="runtime-key",
        base_url="https://api.example.com",
        model="claude-sonnet",
        client_factory=factory,
    )

    result = await client.chat(
        [
            {"role": "system", "content": "System A"},
            {"role": "user", "content": "Question"},
            {"role": "system", "content": "System B"},
        ],
        max_tokens=512,
        max_retries=1,
    )

    assert result == "part onepart two"
    factory.assert_awaited_once_with(
        api_key="runtime-key",
        base_url="https://api.example.com",
        timeout=120.0,
        max_retries=0,
    )
    create.assert_awaited_once_with(
        model="claude-sonnet",
        max_tokens=512,
        system="System A\n\nSystem B",
        messages=[{"role": "user", "content": "Question"}],
    )


def anthropic_status_error(status_code: int, message: str = "upstream error"):
    request = httpx.Request("POST", "https://api.example.com/v1/messages")
    response = httpx.Response(
        status_code,
        request=request,
        headers={"retry-after": "0"},
    )
    return anthropic.APIStatusError(
        message,
        response=response,
        body={"error": {"message": message}},
    )


@pytest.mark.asyncio
async def test_anthropic_structured_output_accepts_markdown_json():
    stream_context = AsyncMessageStream(
        response_with_text('```json\n{"ok": true}\n```')
    )
    stream = MagicMock(return_value=stream_context)
    client = AnthropicLLMClient(
        api_key="runtime-key",
        model="claude-sonnet",
        client_factory=AsyncMock(
            return_value=SimpleNamespace(messages=SimpleNamespace(stream=stream))
        ),
    )

    result = await client.chat_structured(
        messages=[{"role": "user", "content": "Return ok"}],
        output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
        },
        max_retries=1,
    )

    assert result == {"ok": True}
    request = stream.call_args.kwargs
    assert "JSON Schema" in request["system"]
    assert '"ok"' in request["system"]
    assert "Keep the JSON compact" in request["system"]
    assert "8-10 directions" not in request["system"]
    stream_context.get_final_message.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_anthropic_hypothesis_output_preserves_direction_count_constraint():
    stream = MagicMock(
        return_value=AsyncMessageStream(response_with_text('{"directions": []}'))
    )
    client = AnthropicLLMClient(
        api_key="runtime-key",
        model="claude-fable-5",
        client_factory=AsyncMock(
            return_value=SimpleNamespace(messages=SimpleNamespace(stream=stream))
        ),
    )

    await client.chat_structured(
        messages=[{"role": "user", "content": "Return directions"}],
        output_schema={
            "type": "object",
            "properties": {"directions": {"type": "array"}},
        },
        max_retries=1,
    )

    assert "8-10 directions" in stream.call_args.kwargs["system"]


@pytest.mark.asyncio
async def test_anthropic_structured_output_retries_then_succeeds(monkeypatch):
    stream = MagicMock(
        side_effect=[
            RuntimeError("temporary"),
            AsyncMessageStream(response_with_text('{"ok": true}')),
        ],
    )
    sleep = AsyncMock()
    monkeypatch.setattr("app.infrastructure.llm.anthropic_client.asyncio.sleep", sleep)
    client = AnthropicLLMClient(
        api_key="runtime-key",
        model="claude-sonnet",
        client_factory=AsyncMock(
            return_value=SimpleNamespace(messages=SimpleNamespace(stream=stream))
        ),
    )

    result = await client.chat_structured(
        messages=[{"role": "user", "content": "Return ok"}],
        output_schema={"type": "object"},
        max_retries=2,
    )

    assert result == {"ok": True}
    assert stream.call_count == 2
    sleep.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (response_with_text(), "empty response"),
        (response_with_text("not json"), "invalid JSON"),
    ],
)
async def test_anthropic_structured_output_reports_parse_reason(response, reason):
    stream = MagicMock(return_value=AsyncMessageStream(response))
    client = AnthropicLLMClient(
        api_key="runtime-key",
        model="claude-sonnet",
        client_factory=AsyncMock(
            return_value=SimpleNamespace(
                messages=SimpleNamespace(stream=stream)
            )
        ),
    )

    with pytest.raises(LLMError, match=reason) as exc_info:
        await client.chat_structured(
            messages=[{"role": "user", "content": "Return ok"}],
            output_schema={"type": "object"},
            max_retries=1,
        )

    assert exc_info.value.code == (
        "PROVIDER_EMPTY_RESPONSE" if reason == "empty response" else "MODEL_INVALID_JSON"
    )
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_anthropic_structured_output_reports_truncated_json():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"directions": [')],
        stop_reason="max_tokens",
    )
    client = AnthropicLLMClient(
        api_key="runtime-key",
        model="claude-fable-5",
        client_factory=AsyncMock(
            return_value=SimpleNamespace(
                messages=SimpleNamespace(
                    stream=MagicMock(return_value=AsyncMessageStream(response))
                )
            )
        ),
    )

    with pytest.raises(LLMError, match="response truncated.*max_tokens") as exc_info:
        await client.chat_structured(
            messages=[{"role": "user", "content": "Return directions"}],
            output_schema={"type": "object"},
            max_retries=1,
        )

    assert exc_info.value.code == "MODEL_INVALID_JSON"
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (anthropic_status_error(401), "PROVIDER_AUTH_FAILED", False),
        (anthropic_status_error(403), "PROVIDER_PERMISSION_DENIED", False),
        (anthropic_status_error(404), "PROVIDER_MODEL_INVALID", False),
        (anthropic_status_error(400), "PROVIDER_PROTOCOL_MISMATCH", False),
        (anthropic_status_error(413), "PROVIDER_REQUEST_TOO_LARGE", False),
        (anthropic_status_error(429), "PROVIDER_RATE_LIMITED", True),
        (anthropic_status_error(529), "PROVIDER_UPSTREAM_UNAVAILABLE", True),
    ],
)
async def test_anthropic_structured_output_maps_status_errors(
    error, code, retryable
):
    stream = MagicMock(side_effect=error)
    client = AnthropicLLMClient(
        api_key="runtime-key",
        model="claude-sonnet",
        client_factory=AsyncMock(
            return_value=SimpleNamespace(messages=SimpleNamespace(stream=stream))
        ),
    )

    with pytest.raises(LLMError) as exc_info:
        await client.chat_structured(
            messages=[{"role": "user", "content": "Return ok"}],
            output_schema={"type": "object"},
            max_retries=1,
        )

    assert exc_info.value.code == code
    assert exc_info.value.retryable is retryable
    assert exc_info.value.status_code == error.status_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code"),
    [
        (
            anthropic.APITimeoutError(
                httpx.Request("POST", "https://api.example.com/v1/messages")
            ),
            "PROVIDER_MODEL_TASK_TIMEOUT",
        ),
        (
            anthropic.APIConnectionError(
                request=httpx.Request(
                    "POST", "https://api.example.com/v1/messages"
                )
            ),
            "PROVIDER_CONNECTION_FAILED",
        ),
    ],
)
async def test_anthropic_structured_output_maps_transport_errors(error, code):
    client = AnthropicLLMClient(
        api_key="runtime-key",
        model="claude-sonnet",
        client_factory=AsyncMock(
            return_value=SimpleNamespace(
                messages=SimpleNamespace(stream=MagicMock(side_effect=error))
            )
        ),
    )

    with pytest.raises(LLMError) as exc_info:
        await client.chat_structured(
            messages=[{"role": "user", "content": "Return ok"}],
            output_schema={"type": "object"},
            max_retries=1,
        )

    assert exc_info.value.code == code
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_anthropic_non_retryable_error_stops_after_first_attempt(monkeypatch):
    stream = MagicMock(side_effect=anthropic_status_error(401))
    sleep = AsyncMock()
    monkeypatch.setattr("app.infrastructure.llm.anthropic_client.asyncio.sleep", sleep)
    client = AnthropicLLMClient(
        api_key="runtime-key",
        model="claude-sonnet",
        client_factory=AsyncMock(
            return_value=SimpleNamespace(messages=SimpleNamespace(stream=stream))
        ),
    )

    with pytest.raises(LLMError) as exc_info:
        await client.chat_structured(
            messages=[{"role": "user", "content": "Return ok"}],
            output_schema={"type": "object"},
            max_retries=3,
        )

    assert exc_info.value.code == "PROVIDER_AUTH_FAILED"
    assert stream.call_count == 1
    sleep.assert_not_awaited()
