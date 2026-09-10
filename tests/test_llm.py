"""Tests for LLM client utilities — token parameter selection."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import settings
from app.core.exceptions import LLMError
from app.infrastructure import llm as llm_module
from app.infrastructure.llm import (
    OpenAILLMClient,
    _structured_output_max_tokens,
    _temperature_param,
    _token_param,
)
from app.infrastructure.llm.openai_compat import normalize_openai_compatible_base_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://api.example.com", "https://api.example.com/v1"),
        ("https://api.example.com/v1/", "https://api.example.com/v1"),
        (
            "https://api.example.com/v1/chat/completions?x=1#part",
            "https://api.example.com/v1",
        ),
        (
            "https://gateway.example.com/openai/v1/responses",
            "https://gateway.example.com/openai/v1",
        ),
    ],
)
def test_normalize_openai_compatible_base_url(raw, expected):
    assert normalize_openai_compatible_base_url(raw) == expected


@pytest.mark.asyncio
async def test_custom_gpt56_can_use_chat_completions_explicitly():
    client = OpenAILLMClient(
        model="gpt-5.6",
        api_key="secret",
        base_url="https://proxy.example/v1",
        transport_mode="chat_completions",
        structured_output_mode="prompt_json",
    )
    chat_create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
        )
    )
    responses_create = AsyncMock()
    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
        responses=SimpleNamespace(create=responses_create),
    )

    result = await client.chat_structured(
        messages=[{"role": "user", "content": "return JSON"}],
        output_schema={"type": "object"},
        max_tokens=128,
        max_retries=1,
    )

    assert result == {"ok": True}
    chat_create.assert_awaited_once()
    responses_create.assert_not_awaited()
    assert "response_format" not in chat_create.await_args.kwargs


@pytest.mark.asyncio
async def test_openai_compatible_invalid_json_exposes_stable_error_metadata():
    client = OpenAILLMClient(
        model="gpt-5.6",
        api_key="secret",
        base_url="https://proxy.example/v1",
        transport_mode="chat_completions",
        structured_output_mode="prompt_json",
    )
    client._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(
                    return_value=SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content='{"status":')
                            )
                        ]
                    )
                )
            )
        )
    )

    with pytest.raises(LLMError) as exc_info:
        await client.chat_structured(
            messages=[{"role": "user", "content": "return JSON"}],
            output_schema={"type": "object"},
            max_retries=1,
        )

    assert exc_info.value.code == "MODEL_INVALID_JSON"
    assert exc_info.value.retryable is True


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-5.5", 600.0),
        ("gpt-5.5-pro", 600.0),
        ("gpt-5.5-2026-04-23", 600.0),
        (" GPT-5.5-PRO ", 600.0),
        ("gpt-5.6", 600.0),
        ("gpt-5.6-terra", 600.0),
        ("gpt-5.6-sol", 600.0),
        ("gpt-5.4", 120.0),
        ("gpt-4o", 120.0),
    ],
)
def test_structured_report_timeout_is_model_specific(model, expected):
    assert llm_module._structured_report_timeout_seconds(model) == expected


@pytest.mark.parametrize("model", ["gpt-5.5", "gpt-5.5-pro", "gpt-5.6"])
def test_new_gpt_models_get_larger_structured_output_budget(model):
    assert _structured_output_max_tokens(model, 16384) == 32768


def test_older_model_keeps_configured_structured_output_budget():
    assert _structured_output_max_tokens("gpt-5.4", 16384) == 16384


def test_openai_client_bounds_each_request_and_disables_hidden_sdk_retries(
    monkeypatch,
):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    constructor = Mock(return_value=SimpleNamespace())
    monkeypatch.setattr("app.infrastructure.llm.AsyncOpenAI", constructor)

    OpenAILLMClient(model="gpt-4.1")

    constructor.assert_called_once_with(
        api_key="test-key",
        timeout=120.0,
        max_retries=0,
    )


class TestTokenParam:
    """max_completion_tokens vs max_tokens based on model name."""

    def test_gpt4o_uses_max_tokens(self):
        assert _token_param("gpt-4o", 16384) == {"max_tokens": 16384}

    def test_gpt_5_5_uses_max_completion_tokens(self):
        assert _token_param("gpt-5.5", 16384) == {"max_completion_tokens": 16384}

    def test_gpt_5_6_uses_max_completion_tokens(self):
        assert _token_param("gpt-5.6", 8192) == {"max_completion_tokens": 8192}

    def test_gpt_5_6_variants(self):
        for model in ("gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"):
            assert _token_param(model, 4096) == {"max_completion_tokens": 4096}

    def test_gpt_5_5_pro(self):
        assert _token_param("gpt-5.5-pro", 16384) == {"max_completion_tokens": 16384}

    def test_o_series_uses_max_completion_tokens(self):
        for model in ("o1", "o3", "o4"):
            assert _token_param(model, 100000) == {"max_completion_tokens": 100000}

    def test_unknown_model_falls_back_to_max_tokens(self):
        assert _token_param("unknown-model", 100) == {"max_tokens": 100}


class TestTemperatureParam:
    """temperature omission for models that don't support it."""

    def test_gpt4o_includes_temperature(self):
        assert _temperature_param("gpt-4o", 0.3) == {"temperature": 0.3}

    def test_gpt4o_none_omits_temperature(self):
        assert _temperature_param("gpt-4o", None) == {}

    def test_gpt_5_5_omits_temperature(self):
        assert _temperature_param("gpt-5.5", 0.3) == {}

    def test_gpt_5_5_pro_omits_temperature(self):
        assert _temperature_param("gpt-5.5-pro", 0.3) == {}

    def test_o_series_omits_temperature(self):
        assert _temperature_param("o1", 0.3) == {}
        assert _temperature_param("o3", 1.0) == {}

    def test_unknown_model_includes_temperature(self):
        assert _temperature_param("unknown", 0.5) == {"temperature": 0.5}


@pytest.mark.asyncio
async def test_structured_chat_sends_json_schema(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    client = OpenAILLMClient()
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
        )
    )
    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }

    result = await client.chat_structured(
        messages=[{"role": "user", "content": "return JSON"}],
        output_schema=schema,
        schema_name="test_output",
    )

    assert result == {"ok": True}
    assert create.await_args.kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "test_output",
            "strict": True,
            "schema": schema,
        },
    }


@pytest.mark.asyncio
async def test_gpt5_chat_uses_responses_api(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    client = OpenAILLMClient(model="gpt-5.5-pro")
    create = AsyncMock(return_value=SimpleNamespace(output_text="OK"))
    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))

    result = await client.chat(
        messages=[{"role": "user", "content": "reply OK"}],
        max_tokens=64,
        max_retries=1,
    )

    assert result == "OK"
    create.assert_awaited_once_with(
        model="gpt-5.5-pro",
        input=[{"role": "user", "content": "reply OK"}],
        max_output_tokens=64,
    )


@pytest.mark.asyncio
async def test_gpt5_structured_chat_uses_responses_api(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    client = OpenAILLMClient(model="gpt-5.5-pro")
    create = AsyncMock(return_value=SimpleNamespace(output_text='{"ok": true}'))
    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }

    result = await client.chat_structured(
        messages=[{"role": "user", "content": "return JSON"}],
        output_schema=schema,
        max_tokens=128,
        max_retries=1,
    )

    assert result == {"ok": True}
    request = create.await_args.kwargs
    assert request["model"] == "gpt-5.5-pro"
    assert request["max_output_tokens"] == 128
    assert request["input"][0]["role"] == "system"
    assert '"additionalProperties": false' in request["input"][0]["content"]


@pytest.mark.asyncio
async def test_gpt5_structured_chat_uses_larger_default_budget(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    client = OpenAILLMClient(model="gpt-5.6")
    create = AsyncMock(return_value=SimpleNamespace(output_text='{"ok": true}'))
    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))

    await client.chat_structured(
        messages=[{"role": "user", "content": "return JSON"}],
        output_schema={"type": "object"},
        max_retries=1,
    )

    assert create.await_args.kwargs["max_output_tokens"] == 32768


@pytest.mark.asyncio
async def test_gpt5_structured_chat_reports_incomplete_response(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    client = OpenAILLMClient(model="gpt-5.6")
    create = AsyncMock(
        return_value=SimpleNamespace(
            status="incomplete",
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
            output_text='{"ok":',
        )
    )
    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))

    with pytest.raises(LLMError, match="response truncated: max_output_tokens"):
        await client.chat_structured(
            messages=[{"role": "user", "content": "return JSON"}],
            output_schema={"type": "object"},
            max_retries=1,
        )


@pytest.mark.asyncio
async def test_structured_chat_uses_json_object_for_freeform_schema(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    client = OpenAILLMClient(model="gpt-4o")
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"data": {"key": "value"}}'))]
        )
    )
    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    schema = {
        "type": "object",
        "properties": {
            "data": {
                "type": "object",
                "additionalProperties": True,
            }
        },
    }

    result = await client.chat_structured(
        messages=[{"role": "user", "content": "return JSON"}],
        output_schema=schema,
        schema_name="freeform_output",
        max_retries=1,
    )

    assert result == {"data": {"key": "value"}}
    request = create.await_args.kwargs
    assert request["response_format"] == {"type": "json_object"}
    assert request["messages"][0]["role"] == "system"
    assert '"additionalProperties": true' in request["messages"][0]["content"]


@pytest.mark.asyncio
async def test_structured_chat_reports_openai_response_shape_error(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    client = OpenAILLMClient(model="claude-fable-5")
    client._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value="not-openai"))
        )
    )

    with pytest.raises(LLMError, match="OpenAI-compatible response shape invalid"):
        await client.chat_structured(
            messages=[{"role": "user", "content": "return JSON"}],
            output_schema={"type": "object"},
            max_retries=1,
        )


@pytest.mark.asyncio
async def test_structured_chat_exposes_task_timeout_without_duplicate_retry(monkeypatch):
    from openai import APITimeoutError

    from app.core.exceptions import LLMTaskTimeoutError

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    client = OpenAILLMClient(model="gpt-5.5-2026-04-23")
    create = AsyncMock(side_effect=APITimeoutError(request=Mock()))
    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))

    with pytest.raises(LLMTaskTimeoutError) as exc_info:
        await client.chat_structured(
            messages=[{"role": "user", "content": "return JSON"}],
            output_schema={"type": "object"},
            max_retries=1,
        )

    assert exc_info.value.code == "PROVIDER_MODEL_TASK_TIMEOUT"
    assert exc_info.value.retryable is False
    assert exc_info.value.timeout_seconds == 600
    create.assert_awaited_once()
    assert create.await_args.kwargs["timeout"] == 600.0
