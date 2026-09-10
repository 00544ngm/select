from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

import anthropic
import httpx
import pytest
from openai import (
    APIConnectionError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
)

from app.infrastructure.llm.anthropic_client import AnthropicLLMError
from backend.application.provider_clients import (
    ProviderClientResolver,
    ProviderConnectionError,
    ProviderConnectionTester,
    ProviderModelVerifier,
    ProviderResolutionError,
    ProviderRuntimeConfig,
    _default_client_builder,
    classify_provider_error,
)
from backend.security.provider_crypto import ProviderCrypto


@pytest.mark.parametrize(
    ("raw", "status_code", "code", "retryable"),
    [
        (
            "not supported by any configured account in this group",
            404,
            "PROVIDER_MODEL_ROUTE_UNAVAILABLE",
            False,
        ),
        ("model_not_found", 404, "PROVIDER_MODEL_INVALID", False),
        ("rate_limit_error", 429, "PROVIDER_RATE_LIMITED", True),
        ("cloudflare error 502", 502, "PROVIDER_UPSTREAM_UNAVAILABLE", True),
    ],
)
def test_classifies_provider_model_errors(
    raw, status_code, code, retryable
):
    result = classify_provider_error(raw, status_code=status_code)

    assert (result.code, result.retryable) == (code, retryable)
    assert "sk-secret" not in result.message


@pytest.mark.asyncio
async def test_model_verifier_uses_one_structured_probe_for_selected_model():
    client = SimpleNamespace(
        chat_structured=AsyncMock(return_value={"status": "OK"})
    )
    verifier = ProviderModelVerifier(client_builder=lambda _config, _model: client)
    config = ProviderRuntimeConfig(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="anthropic",
        display_name="Compatible Provider",
        role="primary",
        base_url="https://proxy.example",
        default_model="claude-opus-5",
        api_key="secret",
    )

    result = await verifier(config, "claude-opus-5")

    assert result.status == "verified"
    assert result.model == "claude-opus-5"
    assert result.message == "结构化验证成功"
    client.chat_structured.assert_awaited_once()
    assert client.chat_structured.await_args.kwargs["max_retries"] == 1
    assert client.chat_structured.await_args.kwargs["max_tokens"] == 256


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gpt-5.5", "gpt-5.5-pro"])
async def test_model_verifier_accepts_slow_models_with_extended_task_window(
    model,
):
    client = SimpleNamespace(
        chat_structured=AsyncMock(return_value={"status": "ok"})
    )
    builder = Mock(return_value=client)
    verifier = ProviderModelVerifier(client_builder=builder)
    config = ProviderRuntimeConfig(
        slug="openai",
        provider_type="openai",
        api_protocol="openai",
        display_name="OpenAI",
        role="primary",
        base_url="https://api.openai.com/v1",
        default_model=model,
        api_key="redacted",
    )

    result = await verifier(config, model)

    assert result.status == "verified"
    assert result.model == model
    builder.assert_called_once_with(config, model)
    client.chat_structured.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_verifier_probes_maike_anthropic_models_instead_of_blocking_domain():
    client = SimpleNamespace(
        chat_structured=AsyncMock(return_value={"status": "OK"})
    )
    builder = Mock(return_value=client)
    verifier = ProviderModelVerifier(client_builder=builder)
    config = ProviderRuntimeConfig(
        slug="custom",
        provider_type="anthropic",
        api_protocol="anthropic",
        display_name="Maike Claude",
        role="primary",
        base_url="https://maike-ai.top",
        default_model="claude-sonnet-4-6",
        api_key="redacted",
    )

    result = await verifier(config, "claude-sonnet-4-6")

    assert result.status == "verified"
    assert result.error_code is None
    builder.assert_called_once_with(config, "claude-sonnet-4-6")
    client.chat_structured.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "retryable", "status"),
    [
        ("MODEL_INVALID_JSON", True, "temporary_error"),
        ("PROVIDER_RATE_LIMITED", True, "temporary_error"),
        ("PROVIDER_AUTH_FAILED", False, "unavailable"),
    ],
)
async def test_model_verifier_preserves_anthropic_error_metadata(
    code, retryable, status
):
    error = AnthropicLLMError(
        code=code,
        message="safe failure",
        retryable=retryable,
    )
    verifier = ProviderModelVerifier(
        client_builder=lambda _config, _model: SimpleNamespace(
            chat_structured=AsyncMock(side_effect=error)
        )
    )
    config = ProviderRuntimeConfig(
        slug="custom",
        provider_type="anthropic",
        api_protocol="anthropic",
        display_name="Anthropic Proxy",
        role="primary",
        base_url="https://api.example.com",
        default_model="claude-sonnet",
        api_key="redacted",
    )

    result = await verifier(config, "claude-sonnet")

    assert result.status == status
    assert result.error_code == code
    assert result.message == "safe failure"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "status", "code"),
    [
        (
            "Model is not supported by any configured account in this group",
            "unavailable",
            "PROVIDER_MODEL_ROUTE_UNAVAILABLE",
        ),
        (
            "Cloudflare upstream error 502",
            "temporary_error",
            "PROVIDER_UPSTREAM_UNAVAILABLE",
        ),
    ],
)
async def test_model_verifier_classifies_failure_without_switching_model(
    message, status, code
):
    client = SimpleNamespace(chat_structured=AsyncMock(side_effect=RuntimeError(message)))
    built_models = []

    def build(_config, model):
        built_models.append(model)
        return client

    verifier = ProviderModelVerifier(client_builder=build)
    config = ProviderRuntimeConfig(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="openai",
        display_name="Compatible Provider",
        role="primary",
        base_url="https://proxy.example/v1",
        default_model="claude-opus-5",
        api_key="secret",
    )

    result = await verifier(config, "claude-opus-5")

    assert (result.status, result.error_code) == (status, code)
    assert built_models == ["claude-opus-5"]
    client.chat_structured.assert_awaited_once()


class ProbeError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.message = code
        self.retryable = retryable


def custom_openai_config(model: str = "gpt-5.6") -> ProviderRuntimeConfig:
    return ProviderRuntimeConfig(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="openai",
        display_name="Compatible GPT",
        role="primary",
        base_url="https://proxy.example/v1",
        default_model=model,
        api_key="secret",
    )


@pytest.mark.asyncio
async def test_custom_openai_capability_probe_falls_back_to_json_object():
    attempted_modes = []

    def build(config, _model):
        attempted_modes.append(
            (config.transport_mode, config.structured_output_mode)
        )
        outcome = (
            ProbeError("PROVIDER_STRUCTURED_OUTPUT_UNSUPPORTED")
            if config.structured_output_mode == "json_schema"
            else {"status": "OK"}
        )
        return SimpleNamespace(
            chat_structured=AsyncMock(
                side_effect=outcome if isinstance(outcome, Exception) else None,
                return_value=None if isinstance(outcome, Exception) else outcome,
            )
        )

    result = await ProviderModelVerifier(client_builder=build)(
        custom_openai_config(), "gpt-5.6"
    )

    assert result.status == "verified"
    assert result.transport_mode == "chat_completions"
    assert result.structured_output_mode == "json_object"
    assert attempted_modes == [
        ("chat_completions", "json_schema"),
        ("chat_completions", "json_object"),
    ]


@pytest.mark.asyncio
async def test_custom_openai_capability_probe_uses_responses_only_for_endpoint_mismatch():
    attempted_modes = []

    def build(config, _model):
        attempted_modes.append(
            (config.transport_mode, config.structured_output_mode)
        )
        if config.transport_mode == "chat_completions":
            return SimpleNamespace(
                chat_structured=AsyncMock(
                    side_effect=ProbeError("PROVIDER_PROTOCOL_MISMATCH")
                )
            )
        return SimpleNamespace(
            chat_structured=AsyncMock(return_value={"status": "OK"})
        )

    result = await ProviderModelVerifier(client_builder=build)(
        custom_openai_config(), "gpt-5.6"
    )

    assert result.status == "verified"
    assert result.transport_mode == "responses"
    assert result.structured_output_mode == "prompt_json"
    assert attempted_modes == [
        ("chat_completions", "json_schema"),
        ("responses", "prompt_json"),
    ]


@pytest.mark.asyncio
async def test_custom_openai_capability_probe_does_not_fallback_on_rate_limit():
    attempted_modes = []

    def build(config, _model):
        attempted_modes.append(
            (config.transport_mode, config.structured_output_mode)
        )
        return SimpleNamespace(
            chat_structured=AsyncMock(
                side_effect=ProbeError("PROVIDER_RATE_LIMITED", retryable=True)
            )
        )

    result = await ProviderModelVerifier(client_builder=build)(
        custom_openai_config(), "gpt-5.6"
    )

    assert result.status == "temporary_error"
    assert result.error_code == "PROVIDER_RATE_LIMITED"
    assert attempted_modes == [("chat_completions", "json_schema")]


@pytest.mark.asyncio
async def test_connection_tester_uses_minimal_chat_request():
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))]
        )
    )
    models = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(id="model-x"),
                SimpleNamespace(id="gpt-image-1"),
                SimpleNamespace(id="model-y"),
            ]
        )
    )
    client = SimpleNamespace(
        models=SimpleNamespace(list=models),
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    )
    factory = AsyncMock(return_value=client)
    tester = ProviderConnectionTester(client_factory=factory)
    config = ProviderRuntimeConfig(
        slug="custom",
        provider_type="openai_compatible",
        display_name="Internal API",
        role="primary",
        base_url="https://llm.example/v1",
        default_model="model-x",
        api_key="secret",
    )

    result = await tester(config)

    assert result.message == "Connection successful"
    assert result.models == ("model-x", "model-y")
    factory.assert_awaited_once_with(
        api_key="secret",
        base_url="https://llm.example/v1",
        timeout=30.0,
        max_retries=0,
    )
    create.assert_awaited_once_with(
        model="model-x",
        messages=[{"role": "user", "content": "Reply OK"}],
        max_tokens=1,
    )


@pytest.mark.asyncio
async def test_connection_tester_uses_responses_for_gpt5_models():
    responses_create = AsyncMock(return_value=SimpleNamespace(output_text="OK"))
    client = SimpleNamespace(
        models=SimpleNamespace(
            list=AsyncMock(
                return_value=SimpleNamespace(data=[SimpleNamespace(id="gpt-5.4")])
            )
        ),
        responses=SimpleNamespace(create=responses_create),
    )
    tester = ProviderConnectionTester(client_factory=AsyncMock(return_value=client))
    config = ProviderRuntimeConfig(
        slug="openai",
        provider_type="openai",
        display_name="OpenAI",
        role="primary",
        base_url="https://api.openai.com/v1",
        default_model="gpt-5.4",
        api_key="secret",
    )

    result = await tester(config)

    assert result.models == ("gpt-5.4",)
    responses_create.assert_awaited_once_with(
        model="gpt-5.4",
        input="Reply OK",
        max_output_tokens=128,
    )


@pytest.mark.asyncio
async def test_connection_tester_starts_custom_gpt56_with_chat_completions():
    chat_create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))]
        )
    )
    responses_create = AsyncMock()
    client = SimpleNamespace(
        models=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(data=[]))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
        responses=SimpleNamespace(create=responses_create),
    )
    factory = AsyncMock(return_value=client)
    tester = ProviderConnectionTester(client_factory=factory)

    result = await tester(custom_openai_config("gpt-5.6"))

    assert result.message == "Connection successful; model discovery unavailable"
    chat_create.assert_awaited_once_with(
        model="gpt-5.6",
        messages=[{"role": "user", "content": "Reply OK"}],
        max_tokens=1,
    )
    responses_create.assert_not_awaited()
    factory.assert_awaited_once_with(
        api_key="secret",
        base_url="https://proxy.example/v1",
        timeout=30.0,
        max_retries=0,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "message", "expected_code"),
    [
        (
            {"error": {"code": "model_not_found", "message": "model missing"}},
            "model missing",
            "PROVIDER_MODEL_INVALID",
        ),
        (
            {"error": {"type": "not_found_error", "message": "endpoint not found"}},
            "endpoint not found",
            "PROVIDER_PROTOCOL_MISMATCH",
        ),
    ],
)
async def test_connection_tester_distinguishes_model_and_endpoint_404(
    body, message, expected_code
):
    request = httpx.Request("POST", "https://proxy.example/v1/chat/completions")
    response = httpx.Response(404, request=request)
    error = NotFoundError(message, response=response, body=body)
    client = SimpleNamespace(
        models=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(data=[]))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=error))),
        responses=SimpleNamespace(create=AsyncMock(side_effect=error)),
    )
    tester = ProviderConnectionTester(client_factory=AsyncMock(return_value=client))

    with pytest.raises(ProviderConnectionError) as exc_info:
        await tester(custom_openai_config("gpt-5.6"))

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_connection_tester_uses_responses_only_after_custom_chat_endpoint_mismatch():
    request = httpx.Request("POST", "https://proxy.example/v1/chat/completions")
    response = httpx.Response(404, request=request)
    endpoint_error = NotFoundError(
        "endpoint not found",
        response=response,
        body={"error": {"type": "not_found_error", "message": "endpoint not found"}},
    )
    chat_create = AsyncMock(side_effect=endpoint_error)
    responses_create = AsyncMock(return_value=SimpleNamespace(output_text="OK"))
    client = SimpleNamespace(
        models=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(data=[]))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
        responses=SimpleNamespace(create=responses_create),
    )
    tester = ProviderConnectionTester(client_factory=AsyncMock(return_value=client))

    result = await tester(custom_openai_config("gpt-5.6"))

    assert result.message == "Connection successful; model discovery unavailable"
    chat_create.assert_awaited_once()
    responses_create.assert_awaited_once_with(
        model="gpt-5.6",
        input="Reply OK",
        max_output_tokens=128,
    )


@pytest.mark.asyncio
async def test_connection_tester_uses_responses_after_nonstandard_custom_chat_shape():
    chat_create = AsyncMock(return_value="nonstandard")
    responses_create = AsyncMock(return_value=SimpleNamespace(output_text="OK"))
    client = SimpleNamespace(
        models=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(data=[]))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
        responses=SimpleNamespace(create=responses_create),
    )
    tester = ProviderConnectionTester(client_factory=AsyncMock(return_value=client))

    result = await tester(custom_openai_config("gpt-5.6"))

    assert result.message == "Connection successful; model discovery unavailable"
    chat_create.assert_awaited_once()
    responses_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_connection_tester_does_not_try_responses_after_custom_rate_limit():
    request = httpx.Request("POST", "https://proxy.example/v1/chat/completions")
    response = httpx.Response(429, request=request)
    error = RateLimitError(
        "rate limited",
        response=response,
        body={"error": {"type": "rate_limit_error"}},
    )
    responses_create = AsyncMock()
    client = SimpleNamespace(
        models=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(data=[]))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=error))),
        responses=SimpleNamespace(create=responses_create),
    )
    tester = ProviderConnectionTester(client_factory=AsyncMock(return_value=client))

    with pytest.raises(ProviderConnectionError) as exc_info:
        await tester(custom_openai_config("gpt-5.6"))

    assert exc_info.value.code == "PROVIDER_RATE_LIMITED"
    responses_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_connection_tester_gives_deepseek_enough_output_tokens():
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))]
        )
    )
    client = SimpleNamespace(
        models=SimpleNamespace(
            list=AsyncMock(
                return_value=SimpleNamespace(
                    data=[SimpleNamespace(id="deepseek-v4-flash")]
                )
            )
        ),
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    )
    tester = ProviderConnectionTester(client_factory=AsyncMock(return_value=client))
    config = ProviderRuntimeConfig(
        slug="deepseek",
        provider_type="openai_compatible",
        display_name="DeepSeek",
        role="secondary",
        base_url="https://api.deepseek.com",
        default_model="deepseek-v4-flash",
        api_key="secret",
    )

    result = await tester(config)

    assert result.models == ("deepseek-v4-flash",)
    create.assert_awaited_once_with(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Reply OK"}],
        max_tokens=128,
    )


@pytest.mark.asyncio
async def test_connection_tester_keeps_connection_success_when_model_discovery_is_unsupported():
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))]
        )
    )
    client = SimpleNamespace(
        models=SimpleNamespace(list=AsyncMock(side_effect=AttributeError("unsupported"))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    )
    tester = ProviderConnectionTester(client_factory=AsyncMock(return_value=client))
    config = ProviderRuntimeConfig(
        slug="custom",
        provider_type="openai_compatible",
        display_name="Internal API",
        role="primary",
        base_url="https://llm.example/v1",
        default_model="model-x",
        api_key="secret",
    )

    result = await tester(config)

    assert result.message == "Connection successful; model discovery unavailable"
    assert result.models == ()


@pytest.mark.asyncio
async def test_connection_tester_rejects_nonstandard_openai_response_shape():
    chat_create = AsyncMock(return_value="OK")
    responses_create = AsyncMock(return_value="OK")
    client = SimpleNamespace(
        models=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(data=[]))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
        responses=SimpleNamespace(create=responses_create),
    )
    tester = ProviderConnectionTester(client_factory=AsyncMock(return_value=client))
    config = ProviderRuntimeConfig(
        slug="custom",
        provider_type="openai_compatible",
        display_name="Custom API",
        role="primary",
        base_url="https://llm.example/v1",
        default_model="claude-fable-5",
        api_key="secret",
    )

    with pytest.raises(ProviderConnectionError) as exc_info:
        await tester(config)

    assert exc_info.value.code == "PROVIDER_PROTOCOL_MISMATCH"
    assert exc_info.value.retryable is False
    chat_create.assert_awaited_once()
    responses_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_connection_tester_uses_messages_api_for_anthropic_custom_provider():
    create = AsyncMock(
        return_value=SimpleNamespace(
            content=[SimpleNamespace(type="text", text="OK")]
        )
    )
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    anthropic_factory = AsyncMock(return_value=client)
    tester = ProviderConnectionTester(anthropic_client_factory=anthropic_factory)
    config = ProviderRuntimeConfig(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="anthropic",
        display_name="Anthropic Proxy",
        role="primary",
        base_url="https://api.example.com",
        default_model="claude-sonnet",
        api_key="secret",
    )

    result = await tester(config)

    assert result.message == "Connection successful"
    assert result.models == ("claude-sonnet",)
    anthropic_factory.assert_awaited_once_with(
        api_key="secret",
        base_url="https://api.example.com",
        timeout=30.0,
        max_retries=0,
    )
    create.assert_awaited_once_with(
        model="claude-sonnet",
        max_tokens=16,
        messages=[{"role": "user", "content": "Reply OK"}],
    )


def _cattoken_claude_config() -> ProviderRuntimeConfig:
    return ProviderRuntimeConfig(
        slug="cattoken_claude",
        provider_type="anthropic",
        api_protocol="anthropic",
        display_name="CatToken Claude",
        role="primary",
        base_url="https://www.cattoken.vip",
        default_model="claude-sonnet-4-6",
        api_key="redacted",
    )


@pytest.mark.asyncio
async def test_connection_tester_uses_messages_api_for_cattoken_claude():
    create = AsyncMock(
        return_value=SimpleNamespace(
            content=[SimpleNamespace(type="text", text="OK")]
        )
    )
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    anthropic_factory = AsyncMock(return_value=client)
    tester = ProviderConnectionTester(anthropic_client_factory=anthropic_factory)

    result = await tester(_cattoken_claude_config())

    assert result.message == "Connection successful"
    assert result.models == ("claude-sonnet-4-6",)
    anthropic_factory.assert_awaited_once_with(
        api_key="redacted",
        base_url="https://www.cattoken.vip",
        timeout=30.0,
        max_retries=0,
    )
    create.assert_awaited_once_with(
        model="claude-sonnet-4-6",
        max_tokens=16,
        messages=[{"role": "user", "content": "Reply OK"}],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream_error", "code", "retryable", "message"),
    [
        (
            lambda request, response: anthropic.AuthenticationError(
                "upstream credential detail", response=response, body=None
            ),
            "PROVIDER_AUTH_FAILED",
            False,
            "CatToken Claude authentication failed",
        ),
        (
            lambda request, response: anthropic.PermissionDeniedError(
                "upstream permission detail", response=response, body=None
            ),
            "PROVIDER_PERMISSION_DENIED",
            False,
            "CatToken Claude API Key cannot access this model",
        ),
        (
            lambda request, response: anthropic.NotFoundError(
                "upstream model detail", response=response, body=None
            ),
            "PROVIDER_MODEL_INVALID",
            False,
            "CatToken Claude configured model was not found or is unavailable",
        ),
        (
            lambda request, response: anthropic.RateLimitError(
                "upstream rate detail", response=response, body=None
            ),
            "PROVIDER_RATE_LIMITED",
            True,
            "CatToken Claude is rate limited",
        ),
        (
            lambda request, response: anthropic.APIStatusError(
                "upstream status detail", response=response, body=None
            ),
            "PROVIDER_UPSTREAM_UNAVAILABLE",
            True,
            "CatToken Claude 上游服务暂时不可用，请稍后重试",
        ),
        (
            lambda request, response: anthropic.APIConnectionError(
                message="upstream connection detail", request=request
            ),
            "PROVIDER_CONNECTION_FAILED",
            True,
            "无法连接 CatToken Claude，请检查服务地址或稍后重试",
        ),
        (
            lambda request, response: anthropic.APITimeoutError(request=request),
            "PROVIDER_MODEL_TASK_TIMEOUT",
            True,
            "CatToken Claude 请求超时，请稍后重试",
        ),
    ],
    ids=(
        "authentication",
        "permission-denied",
        "not-found",
        "rate-limit",
        "api-status",
        "connection",
        "timeout",
    ),
)
async def test_connection_tester_maps_cattoken_claude_anthropic_errors(
    upstream_error, code, retryable, message
):
    request = httpx.Request(
        "POST",
        "https://www.cattoken.vip/v1/messages",
        headers={"x-test-credential": "redacted"},
    )
    response = httpx.Response(503, request=request)
    client = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(side_effect=upstream_error(request, response))
        )
    )
    tester = ProviderConnectionTester(
        anthropic_client_factory=AsyncMock(return_value=client)
    )

    with pytest.raises(ProviderConnectionError) as exc_info:
        await tester(_cattoken_claude_config())

    assert exc_info.value.code == code
    assert exc_info.value.retryable is retryable
    assert exc_info.value.message == message
    assert "redacted" not in exc_info.value.message
    assert "x-test-credential" not in exc_info.value.message


@pytest.mark.asyncio
async def test_connection_tester_rejects_empty_anthropic_response():
    client = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(return_value=SimpleNamespace(content=[]))
        )
    )
    tester = ProviderConnectionTester(
        anthropic_client_factory=AsyncMock(return_value=client)
    )
    config = ProviderRuntimeConfig(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="anthropic",
        display_name="Anthropic Proxy",
        role="primary",
        base_url="https://api.example.com",
        default_model="claude-sonnet",
        api_key="secret",
    )

    with pytest.raises(ProviderConnectionError) as exc_info:
        await tester(config)

    assert exc_info.value.code == "PROVIDER_EMPTY_RESPONSE"
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_connection_tester_uses_responses_for_cattoken():
    responses_create = AsyncMock(return_value=SimpleNamespace(output_text="OK"))
    client = SimpleNamespace(
        models=SimpleNamespace(
            list=AsyncMock(
                return_value=SimpleNamespace(data=[SimpleNamespace(id="gpt-5.4")])
            )
        ),
        responses=SimpleNamespace(create=responses_create),
    )
    tester = ProviderConnectionTester(client_factory=AsyncMock(return_value=client))
    config = ProviderRuntimeConfig(
        slug="cattoken",
        provider_type="openai_compatible",
        display_name="CatToken",
        role="primary",
        base_url="https://www.cattoken.vip/v1",
        default_model="gpt-5.4",
        api_key="secret",
    )

    result = await tester(config)

    assert result.models == ("gpt-5.4",)
    responses_create.assert_awaited_once_with(
        model="gpt-5.4",
        input="Reply OK",
        max_output_tokens=16,
    )


@pytest.mark.asyncio
async def test_connection_tester_maps_upstream_502_to_retryable_provider_error():
    request = httpx.Request("POST", "https://www.cattoken.vip/v1/responses")
    response = httpx.Response(502, request=request)
    upstream_error = InternalServerError(
        "Upstream service temporarily unavailable",
        response=response,
        body={"error": {"type": "upstream_error"}},
    )
    client = SimpleNamespace(
        models=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(data=[]))),
        responses=SimpleNamespace(create=AsyncMock(side_effect=upstream_error)),
    )
    tester = ProviderConnectionTester(client_factory=AsyncMock(return_value=client))
    config = ProviderRuntimeConfig(
        slug="cattoken",
        provider_type="openai_compatible",
        display_name="CatToken",
        role="primary",
        base_url="https://www.cattoken.vip/v1",
        default_model="gpt-5.4",
        api_key="secret",
    )

    with pytest.raises(ProviderConnectionError) as exc_info:
        await tester(config)

    assert exc_info.value.code == "PROVIDER_UNAVAILABLE"
    assert exc_info.value.message == "CatToken 上游服务暂时不可用，请稍后重试"
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_connection_tester_reports_provider_specific_network_error():
    request = httpx.Request("POST", "https://www.cattoken.vip/v1/responses")
    connection_error = APIConnectionError(request=request)
    client = SimpleNamespace(
        models=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(data=[]))),
        responses=SimpleNamespace(create=AsyncMock(side_effect=connection_error)),
    )
    tester = ProviderConnectionTester(client_factory=AsyncMock(return_value=client))
    config = ProviderRuntimeConfig(
        slug="cattoken",
        provider_type="openai_compatible",
        display_name="CatToken",
        role="primary",
        base_url="https://www.cattoken.vip/v1",
        default_model="gpt-5.4",
        api_key="secret",
    )

    with pytest.raises(ProviderConnectionError) as exc_info:
        await tester(config)

    assert exc_info.value.code == "PROVIDER_UNAVAILABLE"
    assert exc_info.value.message == "无法连接 CatToken，请检查服务地址或稍后重试"
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_resolver_builds_custom_primary_from_encrypted_database_config(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = SimpleNamespace(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="anthropic",
        display_name="Internal API",
        base_url="https://llm.example/v1",
        default_model="configured-model",
        encrypted_api_key=crypto.encrypt("custom-secret"),
        is_enabled=True,
    )
    built = []

    def build(config, model):
        built.append((config, model))
        return "custom-client"

    resolver = ProviderClientResolver(
        repository=repository,
        crypto=crypto,
        legacy_settings=SimpleNamespace(),
        client_builder=build,
    )

    client = await resolver.primary("custom", "requested-model")

    assert client == "custom-client"
    assert built[0][0].api_key == "custom-secret"
    assert built[0][0].base_url == "https://llm.example/v1"
    assert built[0][0].api_protocol == "anthropic"
    assert built[0][1] == "requested-model"


@pytest.mark.asyncio
async def test_resolver_injects_verified_custom_openai_capability(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = SimpleNamespace(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="openai",
        display_name="Compatible GPT",
        base_url="https://proxy.example/v1",
        default_model="gpt-5.6",
        encrypted_api_key=crypto.encrypt("custom-secret"),
        is_enabled=True,
        supported_models=["gpt-5.6"],
        validation_revision=2,
    )
    repository.get_model_validation.return_value = SimpleNamespace(
        status="verified",
        connection_revision=2,
        transport_mode="chat_completions",
        structured_output_mode="prompt_json",
    )
    resolver = ProviderClientResolver(
        repository=repository,
        crypto=crypto,
        legacy_settings=SimpleNamespace(),
        client_builder=lambda config, model: (config, model),
    )

    resolved = await resolver.resolve_primary("custom", "gpt-5.6")

    assert resolved.client[0].transport_mode == "chat_completions"
    assert resolved.client[0].structured_output_mode == "prompt_json"
    repository.get_model_validation.assert_awaited_once_with(
        "custom", "openai", "gpt-5.6"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "validation",
    [
        None,
        SimpleNamespace(
            status="verified",
            connection_revision=1,
            transport_mode="chat_completions",
            structured_output_mode="json_schema",
        ),
        SimpleNamespace(
            status="verified",
            connection_revision=2,
            transport_mode=None,
            structured_output_mode=None,
        ),
    ],
)
async def test_resolver_rejects_custom_openai_without_current_capability(
    tmp_path, validation
):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = SimpleNamespace(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="openai",
        display_name="Compatible GPT",
        base_url="https://proxy.example/v1",
        default_model="gpt-5.6",
        encrypted_api_key=crypto.encrypt("custom-secret"),
        is_enabled=True,
        supported_models=["gpt-5.6"],
        validation_revision=2,
    )
    repository.get_model_validation.return_value = validation
    resolver = ProviderClientResolver(
        repository=repository,
        crypto=crypto,
        legacy_settings=SimpleNamespace(),
    )

    with pytest.raises(ProviderResolutionError) as exc_info:
        await resolver.resolve_primary("custom", "gpt-5.6")

    assert exc_info.value.code == "PROVIDER_MODEL_NOT_VERIFIED"


def test_default_client_builder_passes_modes_only_to_custom_openai():
    config = ProviderRuntimeConfig(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="openai",
        display_name="Compatible GPT",
        role="primary",
        base_url="https://proxy.example/v1",
        default_model="gpt-5.6",
        api_key="secret",
        transport_mode="chat_completions",
        structured_output_mode="prompt_json",
    )

    with patch("app.infrastructure.llm.OpenAILLMClient") as client_class:
        built = _default_client_builder(config, "gpt-5.6")

    assert built is client_class.return_value
    client_class.assert_called_once_with(
        model="gpt-5.6",
        api_key="secret",
        base_url="https://proxy.example/v1",
        transport_mode="chat_completions",
        structured_output_mode="prompt_json",
    )


@pytest.mark.asyncio
async def test_resolver_exposes_selected_provider_and_model_without_changing_primary(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = SimpleNamespace(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="anthropic",
        display_name="Internal API",
        base_url="https://llm.example/v1",
        default_model="configured-model",
        encrypted_api_key=crypto.encrypt("custom-secret"),
        is_enabled=True,
        supported_models=["configured-model"],
    )
    client = object()
    resolver = ProviderClientResolver(
        repository=repository,
        crypto=crypto,
        legacy_settings=SimpleNamespace(),
        client_builder=lambda config, model: client,
    )

    resolved = await resolver.resolve_primary("custom", None)

    assert resolved.client is client
    assert resolved.provider == "custom"
    assert resolved.model == "configured-model"
    assert await resolver.primary("custom", None) is client


@pytest.mark.asyncio
async def test_resolver_returns_none_when_deepseek_secondary_is_not_configured(tmp_path):
    resolver = ProviderClientResolver(
        repository=AsyncMock(get=AsyncMock(return_value=None)),
        crypto=ProviderCrypto(key_file=tmp_path / "provider.key"),
        legacy_settings=SimpleNamespace(deepseek_api_key=""),
    )

    assert await resolver.secondary_deepseek() is None


@pytest.mark.asyncio
async def test_resolver_ignores_unreadable_optional_deepseek_credential(tmp_path):
    from cryptography.fernet import Fernet

    writer = ProviderCrypto(
        key_file=tmp_path / "writer.key",
        configured_key=Fernet.generate_key().decode(),
    )
    reader = ProviderCrypto(
        key_file=tmp_path / "reader.key",
        configured_key=Fernet.generate_key().decode(),
    )
    repository = AsyncMock()
    repository.get.return_value = SimpleNamespace(
        slug="deepseek",
        provider_type="openai_compatible",
        api_protocol="openai",
        display_name="DeepSeek",
        base_url="https://api.deepseek.example/v1",
        default_model="deepseek-chat",
        encrypted_api_key=writer.encrypt("stale-secret"),
        is_enabled=True,
        supported_models=["deepseek-chat"],
    )
    resolver = ProviderClientResolver(
        repository=repository,
        crypto=reader,
        legacy_settings=SimpleNamespace(),
    )

    assert await resolver.resolve_secondary_deepseek() is None


@pytest.mark.asyncio
async def test_resolver_exposes_deepseek_secondary_provider_and_model(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = SimpleNamespace(
        slug="deepseek",
        provider_type="openai_compatible",
        api_protocol="openai",
        display_name="DeepSeek",
        base_url="https://api.deepseek.example/v1",
        default_model="deepseek-reasoner",
        encrypted_api_key=crypto.encrypt("deepseek-secret"),
        is_enabled=True,
        supported_models=["deepseek-reasoner"],
    )
    client = object()
    resolver = ProviderClientResolver(
        repository=repository,
        crypto=crypto,
        legacy_settings=SimpleNamespace(),
        client_builder=lambda config, model: client,
    )

    resolved = await resolver.resolve_secondary_deepseek()

    assert resolved.client is client
    assert resolved.provider == "deepseek"
    assert resolved.model == "deepseek-reasoner"


@pytest.mark.asyncio
async def test_resolver_accepts_deepseek_as_an_explicit_cross_review_provider(tmp_path):
    from cryptography.fernet import Fernet

    crypto = ProviderCrypto(key_file=tmp_path / "key", configured_key=Fernet.generate_key().decode())
    repository = AsyncMock()
    repository.get.return_value = SimpleNamespace(
        slug="deepseek",
        provider_type="openai_compatible",
        display_name="DeepSeek",
        api_protocol="openai",
        role="secondary",
        base_url="https://api.deepseek.example/v1",
        default_model="deepseek-chat",
        encrypted_api_key=crypto.encrypt("deepseek-secret"),
        supported_models=["deepseek-chat"],
        is_enabled=True,
    )
    resolver = ProviderClientResolver(
        repository=repository,
        crypto=crypto,
        legacy_settings=SimpleNamespace(),
    )

    resolved = await resolver.resolve_primary("deepseek", "deepseek-chat")

    assert resolved.provider == "deepseek"
    assert resolved.model == "deepseek-chat"


def test_default_client_builder_uses_anthropic_client_for_custom_protocol():
    config = ProviderRuntimeConfig(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="anthropic",
        display_name="Anthropic Proxy",
        role="primary",
        base_url="https://api.example.com",
        default_model="claude-sonnet",
        api_key="secret",
    )

    with patch("app.infrastructure.llm.AnthropicLLMClient") as client_class:
        built = _default_client_builder(config, "claude-sonnet")

    assert built is client_class.return_value
    client_class.assert_called_once_with(
        model="claude-sonnet",
        api_key="secret",
        base_url="https://api.example.com",
    )


def test_default_client_builder_routes_cattoken_variants_to_their_protocol_clients():
    cattoken = ProviderRuntimeConfig(
        slug="cattoken",
        provider_type="openai_compatible",
        display_name="CatToken OpenAI",
        role="primary",
        base_url="https://www.cattoken.vip/v1",
        default_model="gpt-5.4",
        api_key="redacted",
    )
    cattoken_claude = _cattoken_claude_config()

    with (
        patch("app.infrastructure.llm.AnthropicLLMClient") as anthropic_client,
        patch("app.infrastructure.llm.CatTokenLLMClient") as cattoken_client,
    ):
        built_cattoken = _default_client_builder(cattoken, "gpt-5.4")
        built_cattoken_claude = _default_client_builder(
            cattoken_claude, "claude-sonnet-4-6"
        )

    assert built_cattoken is cattoken_client.return_value
    assert built_cattoken_claude is anthropic_client.return_value
    cattoken_client.assert_called_once_with(
        model="gpt-5.4",
        api_key="redacted",
        base_url="https://www.cattoken.vip/v1",
    )
    anthropic_client.assert_called_once_with(
        model="claude-sonnet-4-6",
        api_key="redacted",
        base_url="https://www.cattoken.vip",
    )


@pytest.mark.asyncio
@pytest.mark.skip(reason="CatToken providers are retired")
async def test_resolver_requires_database_config_for_cattoken_claude(tmp_path):
    resolver = ProviderClientResolver(
        repository=AsyncMock(get=AsyncMock(return_value=None)),
        crypto=ProviderCrypto(key_file=tmp_path / "provider.key"),
        legacy_settings=SimpleNamespace(cattoken_claude_api_key="redacted"),
    )

    with pytest.raises(ProviderResolutionError) as exc_info:
        await resolver.resolve_primary("cattoken_claude", None)

    assert exc_info.value.code == "PROVIDER_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_resolver_keeps_custom_not_configured_message(tmp_path):
    resolver = ProviderClientResolver(
        repository=AsyncMock(get=AsyncMock(return_value=None)),
        crypto=ProviderCrypto(key_file=tmp_path / "provider.key"),
        legacy_settings=SimpleNamespace(),
    )

    with pytest.raises(ProviderResolutionError) as exc_info:
        await resolver.resolve_primary("custom", None)

    assert exc_info.value.code == "PROVIDER_NOT_CONFIGURED"
    assert exc_info.value.message == "The custom provider is not configured"


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", ["cattoken", "cattoken_claude"])
async def test_resolver_rejects_retired_cattoken_before_repository_lookup(
    tmp_path, slug
):
    repository = AsyncMock()
    resolver = ProviderClientResolver(
        repository=repository,
        crypto=ProviderCrypto(key_file=tmp_path / "provider.key"),
        legacy_settings=SimpleNamespace(),
    )

    with pytest.raises(ProviderResolutionError) as exc_info:
        await resolver.resolve_primary(slug, None)

    assert exc_info.value.code == "PROVIDER_RETIRED"
    assert exc_info.value.retryable is False
    repository.get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.skip(reason="CatToken providers are retired")
async def test_resolver_builds_cattoken_claude_database_config_with_anthropic_client(
    tmp_path,
):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = SimpleNamespace(
        slug="cattoken_claude",
        provider_type="anthropic",
        api_protocol="anthropic",
        display_name="CatToken Claude",
        base_url="https://www.cattoken.vip",
        default_model="claude-sonnet-4-6",
        encrypted_api_key=crypto.encrypt("redacted"),
        is_enabled=True,
        supported_models=["claude-sonnet-4-6", "claude-opus-4-6"],
    )
    resolver = ProviderClientResolver(
        repository=repository,
        crypto=crypto,
        legacy_settings=SimpleNamespace(),
    )

    with patch("app.infrastructure.llm.AnthropicLLMClient") as client_class:
        resolved_default = await resolver.resolve_primary("cattoken_claude", None)
        resolved_explicit = await resolver.resolve_primary(
            "cattoken_claude", "claude-opus-4-6"
        )
        with pytest.raises(ProviderResolutionError) as exc_info:
            await resolver.resolve_primary("cattoken_claude", "unsupported-model")

    assert resolved_default.client is client_class.return_value
    assert (resolved_default.provider, resolved_default.model) == (
        "cattoken_claude",
        "claude-sonnet-4-6",
    )
    assert resolved_explicit.client is client_class.return_value
    assert (resolved_explicit.provider, resolved_explicit.model) == (
        "cattoken_claude",
        "claude-opus-4-6",
    )
    assert exc_info.value.code == "PROVIDER_MODEL_INVALID"
    assert client_class.call_args_list == [
        call(
            model="claude-sonnet-4-6",
            api_key="redacted",
            base_url="https://www.cattoken.vip",
        ),
        call(
            model="claude-opus-4-6",
            api_key="redacted",
            base_url="https://www.cattoken.vip",
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gpt-5.5", "gpt-5.5-pro"])
async def test_resolver_accepts_verified_official_openai_slow_models(
    tmp_path,
    model,
):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = SimpleNamespace(
        slug="openai",
        provider_type="openai",
        api_protocol="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model=model,
        encrypted_api_key=crypto.encrypt("redacted"),
        is_enabled=True,
        supported_models=[model, "gpt-5.4"],
    )
    resolver = ProviderClientResolver(
        repository=repository,
        crypto=crypto,
        legacy_settings=SimpleNamespace(),
        client_builder=lambda config, selected_model: (config, selected_model),
    )

    resolved = await resolver.resolve_primary("openai", model)

    assert resolved.provider == "openai"
    assert resolved.model == model
    assert resolved.client[1] == model


@pytest.mark.asyncio
@pytest.mark.skip(reason="CatToken providers are retired")
async def test_resolver_keeps_cattoken_legacy_config_and_identity(tmp_path):
    resolver = ProviderClientResolver(
        repository=AsyncMock(get=AsyncMock(return_value=None)),
        crypto=ProviderCrypto(key_file=tmp_path / "provider.key"),
        legacy_settings=SimpleNamespace(
            cattoken_api_key="redacted",
            cattoken_base_url="https://legacy.cattoken.example/v1",
            cattoken_model="legacy-gpt",
        ),
        client_builder=lambda config, model: (config, model),
    )

    resolved = await resolver.resolve_primary("cattoken", None)

    assert resolved.provider == "cattoken"
    assert resolved.model == "legacy-gpt"
    assert resolved.client[0].display_name == "CatToken"
    assert resolved.client[0].base_url == "https://legacy.cattoken.example/v1"
