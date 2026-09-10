from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import LLMError
from app.infrastructure import llm as llm_module


def test_cattoken_client_accepts_runtime_credentials(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm_module, "AsyncOpenAI", FakeOpenAI)

    llm_module.CatTokenLLMClient(
        api_key="runtime-key",
        base_url="https://proxy.example/v1",
        model="gpt-5.4",
    )

    assert captured == {
        "api_key": "runtime-key",
        "base_url": "https://proxy.example/v1",
    }


def test_openai_client_keeps_env_defaults_when_runtime_values_are_omitted(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm_module, "AsyncOpenAI", FakeOpenAI)
    monkeypatch.setattr(llm_module.settings, "openai_api_key", "env-key")

    llm_module.OpenAILLMClient(model="gpt-4o")

    assert captured == {
        "api_key": "env-key",
        "timeout": 120.0,
        "max_retries": 0,
    }


@pytest.mark.asyncio
async def test_cattoken_chat_uses_responses(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(output_text="OK"))

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(llm_module, "AsyncOpenAI", FakeOpenAI)
    client = llm_module.CatTokenLLMClient(api_key="runtime-key", model="gpt-5.4")

    assert await client.chat([{"role": "user", "content": "Reply OK"}], max_retries=1) == "OK"
    create.assert_awaited_once_with(
        model="gpt-5.4",
        input=[{"role": "user", "content": "Reply OK"}],
        max_output_tokens=16384,
    )


@pytest.mark.asyncio
async def test_cattoken_structured_output_uses_responses_without_schema_parameter(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(output_text='{"ok": true}'))

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(llm_module, "AsyncOpenAI", FakeOpenAI)
    client = llm_module.CatTokenLLMClient(
        api_key="runtime-key",
        base_url="https://proxy.example/v1",
        model="gpt-5.4",
    )

    result = await client.chat_structured(
        messages=[{"role": "user", "content": "Return ok"}],
        output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
        max_retries=1,
    )

    assert result == {"ok": True}
    create.assert_awaited_once()
    request = create.await_args.kwargs
    assert "text" not in request
    assert "properties" in request["input"][0]["content"]


@pytest.mark.asyncio
async def test_cattoken_structured_output_retries_responses(monkeypatch):
    create = AsyncMock(
        side_effect=[
            RuntimeError("temporary upstream failure"),
            SimpleNamespace(output_text='{"ok": true}'),
        ]
    )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(llm_module, "AsyncOpenAI", FakeOpenAI)
    client = llm_module.CatTokenLLMClient(
        api_key="runtime-key",
        base_url="https://proxy.example/v1",
        model="gpt-5.4",
    )

    result = await client.chat_structured(
        messages=[{"role": "user", "content": "Return ok"}],
        output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        max_retries=2,
    )

    assert result == {"ok": True}
    assert create.await_count == 2


@pytest.mark.asyncio
async def test_cattoken_structured_output_accepts_markdown_json(monkeypatch):
    create = AsyncMock(
        return_value=SimpleNamespace(output_text='```json\n{"ok": true}\n```')
    )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(llm_module, "AsyncOpenAI", FakeOpenAI)
    client = llm_module.CatTokenLLMClient(api_key="runtime-key", model="gpt-5.5")

    result = await client.chat_structured(
        messages=[{"role": "user", "content": "Return ok"}],
        output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        max_retries=1,
    )

    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_cattoken_structured_output_reports_empty_response(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(output_text=""))

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(llm_module, "AsyncOpenAI", FakeOpenAI)
    client = llm_module.CatTokenLLMClient(api_key="runtime-key", model="gpt-5.5")

    with pytest.raises(LLMError, match="empty response"):
        await client.chat_structured(
            messages=[{"role": "user", "content": "Return ok"}],
            output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
            max_retries=1,
        )


@pytest.mark.asyncio
async def test_cattoken_structured_output_reports_parse_reason(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(output_text="not json"))

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(create=create)

    monkeypatch.setattr(llm_module, "AsyncOpenAI", FakeOpenAI)
    client = llm_module.CatTokenLLMClient(api_key="runtime-key", model="gpt-5.5")

    with pytest.raises(LLMError, match="invalid JSON"):
        await client.chat_structured(
            messages=[{"role": "user", "content": "Return ok"}],
            output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
            max_retries=1,
        )
