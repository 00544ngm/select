from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Literal

import anthropic
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from app.infrastructure.llm.openai_compat import classify_openai_compatible_error
from backend.db.provider_repository import ProviderConfigurationRepository
from backend.security.provider_crypto import ProviderCrypto, ProviderDecryptionError

RETIRED_PROVIDER_SLUGS = frozenset({"cattoken", "cattoken_claude"})


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    slug: str
    provider_type: str
    display_name: str
    role: Literal["primary", "secondary"]
    base_url: str | None
    default_model: str
    api_key: str
    api_protocol: Literal["openai", "anthropic"] = "openai"
    supported_models: tuple[str, ...] = ()
    transport_mode: Literal["chat_completions", "responses"] | None = None
    structured_output_mode: Literal["json_schema", "json_object", "prompt_json"] | None = None
    connection_revision: int = 1


@dataclass(frozen=True)
class ResolvedProviderClient:
    client: Any
    provider: str
    model: str


@dataclass(frozen=True)
class ProviderConnectionTestResult:
    message: str
    models: tuple[str, ...]


@dataclass(frozen=True)
class ProviderErrorClassification:
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class ProviderModelVerificationResult:
    model: str
    status: Literal["verified", "unavailable", "temporary_error"]
    message: str
    error_code: str | None = None
    transport_mode: Literal["chat_completions", "responses"] | None = None
    structured_output_mode: Literal["json_schema", "json_object", "prompt_json"] | None = None


def classify_provider_error(
    raw: str, *, status_code: int | None
) -> ProviderErrorClassification:
    normalized = raw.lower()
    if "not supported by any configured account" in normalized:
        return ProviderErrorClassification(
            "PROVIDER_MODEL_ROUTE_UNAVAILABLE",
            "中转站当前账号分组没有该模型的可用渠道",
            False,
        )
    if status_code == 401 or "authentication" in normalized:
        return ProviderErrorClassification(
            "PROVIDER_AUTH_FAILED", "API Key 无效或没有访问该模型的权限", False
        )
    if status_code == 403 or "permission_denied" in normalized:
        return ProviderErrorClassification(
            "PROVIDER_PERMISSION_DENIED", "API Key 没有访问该模型的权限", False
        )
    if status_code == 404 or any(
        token in normalized for token in ("model_not_found", "not found")
    ):
        return ProviderErrorClassification(
            "PROVIDER_MODEL_INVALID", "当前模型不存在或暂不可用", False
        )
    if status_code == 429 or "rate_limit" in normalized:
        return ProviderErrorClassification(
            "PROVIDER_RATE_LIMITED", "中转站请求过于频繁，请稍后重试", True
        )
    if status_code == 413:
        return ProviderErrorClassification(
            "PROVIDER_REQUEST_TOO_LARGE", "请求内容超过上游服务限制", False
        )
    if status_code == 400:
        return ProviderErrorClassification(
            "PROVIDER_PROTOCOL_MISMATCH",
            "服务未接受 Anthropic Messages API 请求，请检查接口协议",
            False,
        )
    if (isinstance(status_code, int) and status_code >= 500) or any(
        token in normalized for token in ("error 502", "error 503", "cloudflare")
    ):
        return ProviderErrorClassification(
            "PROVIDER_UPSTREAM_UNAVAILABLE",
            "中转站或其上游模型渠道暂时不可用",
            True,
        )
    return ProviderErrorClassification(
        "PROVIDER_UNAVAILABLE", "模型验证暂时失败，请检查接口配置后重试", True
    )


def _classify_exception(error: Exception) -> ProviderErrorClassification:
    code = getattr(error, "code", None)
    retryable = getattr(error, "retryable", None)
    message = getattr(error, "message", None)
    if isinstance(code, str) and isinstance(retryable, bool):
        return ProviderErrorClassification(
            code,
            str(message or code),
            retryable,
        )
    current: BaseException | None = error
    parts: list[str] = []
    status_code: int | None = None
    for _ in range(6):
        if current is None:
            break
        parts.append(str(current))
        candidate = getattr(current, "status_code", None)
        if status_code is None and isinstance(candidate, int):
            status_code = candidate
        current = current.__cause__
    return classify_provider_error(" ".join(parts), status_code=status_code)


class ProviderConnectionError(RuntimeError):
    def __init__(self, *, code: str, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class ProviderConnectionTester:
    def __init__(
        self,
        *,
        client_factory: Callable[..., Any] = AsyncOpenAI,
        anthropic_client_factory: Callable[..., Any] = anthropic.AsyncAnthropic,
    ) -> None:
        self._client_factory = client_factory
        self._anthropic_client_factory = anthropic_client_factory

    async def __call__(self, config: ProviderRuntimeConfig) -> ProviderConnectionTestResult:
        if config.api_protocol == "anthropic":
            return await self._test_anthropic(config)
        return await self._test_openai(config)

    async def _test_openai(
        self, config: ProviderRuntimeConfig
    ) -> ProviderConnectionTestResult:
        client_args: dict[str, Any] = {
            "api_key": config.api_key,
            "timeout": 30.0,
            "max_retries": 0,
        }
        if config.base_url:
            client_args["base_url"] = config.base_url

        models: tuple[str, ...] = ()
        try:
            client = self._client_factory(**client_args)
            if inspect.isawaitable(client):
                client = await client
            models = await self._discover_models(client)
            if config.slug == "cattoken" or (
                config.slug == "openai"
                and config.default_model.startswith("gpt-5.")
            ):
                response_text = await self._test_responses_request(client, config)
            else:
                try:
                    response_text = await self._test_chat_request(client, config)
                except Exception as error:
                    error_code = getattr(error, "code", None)
                    if not isinstance(error_code, str):
                        error_code = classify_openai_compatible_error(error).code
                    if (
                        config.slug != "custom"
                        or error_code != "PROVIDER_PROTOCOL_MISMATCH"
                    ):
                        raise
                    response_text = await self._test_responses_request(client, config)
            if not isinstance(response_text, str) or not response_text.strip():
                raise ProviderConnectionError(
                    code="PROVIDER_EMPTY_RESPONSE",
                    message=f"{config.display_name} returned an empty response",
                    retryable=True,
                )
            return ProviderConnectionTestResult(
                message=(
                    "Connection successful"
                    if models
                    else "Connection successful; model discovery unavailable"
                ),
                models=models,
            )
        except ProviderConnectionError as error:
            if self._should_degrade(
                config.slug,
                retryable=error.retryable,
                code=error.code,
                models=models,
            ):
                return self._degraded_result(config, models, error.code)
            raise
        except (
            AuthenticationError,
            PermissionDeniedError,
            NotFoundError,
            RateLimitError,
            InternalServerError,
            APITimeoutError,
            APIConnectionError,
        ) as error:
            classified = classify_openai_compatible_error(error)
            if config.slug == "cattoken" and classified.retryable:
                message = (
                    f"无法连接 {config.display_name}，请检查服务地址或稍后重试"
                    if classified.code == "PROVIDER_CONNECTION_FAILED"
                    else f"{config.display_name} 上游服务暂时不可用，请稍后重试"
                )
                raise ProviderConnectionError(
                    code="PROVIDER_UNAVAILABLE",
                    message=message,
                    retryable=True,
                ) from error
            if self._should_degrade(
                config.slug,
                retryable=classified.retryable,
                code=classified.code,
                models=models,
            ):
                return self._degraded_result(config, models, classified.code)
            raise ProviderConnectionError(
                code=classified.code,
                message=classified.message,
                retryable=classified.retryable,
            ) from error

    @staticmethod
    def _should_degrade(
        slug: str,
        *,
        retryable: bool,
        code: str,
        models: tuple[str, ...],
    ) -> bool:
        """Whether a connection-test failure should degrade to a catalog result.

        Retryable upstream/rate-limit/connection failures degrade whenever a
        catalog was discovered (users can still pick an available model). A
        ``PROVIDER_MODEL_INVALID`` (404) failure only degrades for the custom
        slot: a fresh install's default model is the slot template value
        (``gpt-4o``), which many third-party upstreams do not serve — hard
        failing there locks a new install out of configuration. For official
        slots the 404 stays a hard error so a deliberately wrong model is
        reported clearly.
        """
        if slug == "cattoken" or not models:
            return False
        if code == "PROVIDER_MODEL_INVALID":
            return slug == "custom"
        return retryable

    @staticmethod
    def _degraded_result(
        config: ProviderRuntimeConfig,
        models: tuple[str, ...],
        error_code: str,
    ) -> ProviderConnectionTestResult:
        return ProviderConnectionTestResult(
            message=(
                f"连接成功，发现 {len(models)} 个模型；"
                f"默认模型 {config.default_model} 当前不可用（{error_code}），"
                "请在下方选择其它模型并验证"
            ),
            models=models,
        )

    @staticmethod
    async def _test_chat_request(client: Any, config: ProviderRuntimeConfig) -> str | None:
        token_param = {"max_tokens": 128 if config.slug == "deepseek" else 1}
        response = await client.chat.completions.create(
            model=config.default_model,
            messages=[{"role": "user", "content": "Reply OK"}],
            **token_param,
        )
        try:
            return response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as error:
            raise ProviderConnectionError(
                code="PROVIDER_PROTOCOL_MISMATCH",
                message=(
                    f"{config.display_name} did not return an OpenAI-compatible "
                    "response; choose the matching API protocol"
                ),
                retryable=False,
            ) from error

    @staticmethod
    async def _test_responses_request(
        client: Any, config: ProviderRuntimeConfig
    ) -> str | None:
        response = await client.responses.create(
            model=config.default_model,
            input="Reply OK",
            max_output_tokens=(16 if config.slug == "cattoken" else 128),
        )
        try:
            return response.output_text
        except AttributeError as error:
            raise ProviderConnectionError(
                code="PROVIDER_PROTOCOL_MISMATCH",
                message=(
                    f"{config.display_name} did not return an OpenAI-compatible "
                    "response; choose the matching API protocol"
                ),
                retryable=False,
            ) from error

    async def _test_anthropic(
        self, config: ProviderRuntimeConfig
    ) -> ProviderConnectionTestResult:
        client_args: dict[str, Any] = {
            "api_key": config.api_key,
            "timeout": 30.0,
            "max_retries": 0,
        }
        if config.base_url:
            client_args["base_url"] = config.base_url
        try:
            client = self._anthropic_client_factory(**client_args)
            if inspect.isawaitable(client):
                client = await client
            response = await client.messages.create(
                model=config.default_model,
                max_tokens=16,
                messages=[{"role": "user", "content": "Reply OK"}],
            )
            has_text = any(
                getattr(block, "type", None) == "text"
                and bool(str(getattr(block, "text", "")).strip())
                for block in getattr(response, "content", [])
            )
            if not has_text:
                raise ProviderConnectionError(
                    code="PROVIDER_EMPTY_RESPONSE",
                    message=f"{config.display_name} returned an empty response",
                    retryable=True,
                )
            return ProviderConnectionTestResult(
                message="Connection successful",
                models=(config.default_model,),
            )
        except ProviderConnectionError:
            raise
        except anthropic.AuthenticationError as error:
            raise ProviderConnectionError(
                code="PROVIDER_AUTH_FAILED",
                message=f"{config.display_name} authentication failed",
                retryable=False,
            ) from error
        except anthropic.PermissionDeniedError as error:
            raise ProviderConnectionError(
                code="PROVIDER_PERMISSION_DENIED",
                message=f"{config.display_name} API Key cannot access this model",
                retryable=False,
            ) from error
        except anthropic.NotFoundError as error:
            raise ProviderConnectionError(
                code="PROVIDER_MODEL_INVALID",
                message=(
                    f"{config.display_name} configured model was not found or is unavailable"
                ),
                retryable=False,
            ) from error
        except anthropic.RateLimitError as error:
            raise ProviderConnectionError(
                code="PROVIDER_RATE_LIMITED",
                message=f"{config.display_name} is rate limited",
                retryable=True,
            ) from error
        except anthropic.APITimeoutError as error:
            raise ProviderConnectionError(
                code="PROVIDER_MODEL_TASK_TIMEOUT",
                message=f"{config.display_name} 请求超时，请稍后重试",
                retryable=True,
            ) from error
        except anthropic.APIConnectionError as error:
            raise ProviderConnectionError(
                code="PROVIDER_CONNECTION_FAILED",
                message=f"无法连接 {config.display_name}，请检查服务地址或稍后重试",
                retryable=True,
            ) from error
        except anthropic.APIStatusError as error:
            classified = classify_provider_error(
                str(error), status_code=getattr(error, "status_code", None)
            )
            raise ProviderConnectionError(
                code=classified.code,
                message=f"{config.display_name} 上游服务暂时不可用，请稍后重试",
                retryable=classified.retryable,
            ) from error

    @staticmethod
    async def _discover_models(client: Any) -> tuple[str, ...]:
        try:
            response = await client.models.list()
            models = [
                item.id
                for item in response.data
                if isinstance(getattr(item, "id", None), str)
                and _is_task_model(item.id)
            ]
        except Exception:  # noqa: BLE001 - model discovery is optional across providers
            return ()
        return tuple(dict.fromkeys(models))


def _is_task_model(model: str) -> bool:
    excluded = (
        "audio",
        "realtime",
        "image",
        "embedding",
        "moderation",
        "tts",
        "transcription",
        "whisper",
        "dall-e",
    )
    return not any(term in model.lower() for term in excluded)


class ProviderResolutionError(RuntimeError):
    def __init__(self, *, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def _default_client_builder(config: ProviderRuntimeConfig, model: str):
    from app.infrastructure.llm import (
        AnthropicLLMClient,
        CatTokenLLMClient,
        DeepSeekLLMClient,
        OpenAILLMClient,
    )

    kwargs = {
        "model": model,
        "api_key": config.api_key,
        "base_url": config.base_url,
    }
    if config.slug == "cattoken":
        return CatTokenLLMClient(**kwargs)
    if config.slug == "cattoken_claude":
        return AnthropicLLMClient(**kwargs)
    if config.slug == "deepseek":
        return DeepSeekLLMClient(**kwargs)
    if config.slug == "custom" and config.api_protocol == "anthropic":
        return AnthropicLLMClient(**kwargs)
    if config.slug == "custom" and config.api_protocol == "openai":
        return OpenAILLMClient(
            **kwargs,
            transport_mode=config.transport_mode,
            structured_output_mode=config.structured_output_mode,
        )
    if config.api_protocol == "anthropic":
        return AnthropicLLMClient(**kwargs)
    return OpenAILLMClient(**kwargs)


class ProviderModelVerifier:
    def __init__(
        self,
        *,
        client_builder: Callable[[ProviderRuntimeConfig, str], Any] = _default_client_builder,
    ) -> None:
        self._client_builder = client_builder

    async def __call__(
        self, config: ProviderRuntimeConfig, model: str
    ) -> ProviderModelVerificationResult:
        if config.slug == "custom" and config.api_protocol == "openai":
            return await self._verify_custom_openai(config, model)
        return await self._verify_once(config, model)

    async def _verify_custom_openai(
        self, config: ProviderRuntimeConfig, model: str
    ) -> ProviderModelVerificationResult:
        chat_modes = ("json_schema", "json_object", "prompt_json")
        for structured_mode in chat_modes:
            probe_config = replace(
                config,
                transport_mode="chat_completions",
                structured_output_mode=structured_mode,
            )
            result = await self._verify_once(probe_config, model)
            if result.status == "verified":
                return replace(
                    result,
                    transport_mode="chat_completions",
                    structured_output_mode=structured_mode,
                )
            if result.error_code == "PROVIDER_PROTOCOL_MISMATCH":
                break
            if result.error_code != "PROVIDER_STRUCTURED_OUTPUT_UNSUPPORTED":
                return result

        responses_config = replace(
            config,
            transport_mode="responses",
            structured_output_mode="prompt_json",
        )
        result = await self._verify_once(responses_config, model)
        if result.status == "verified":
            return replace(
                result,
                transport_mode="responses",
                structured_output_mode="prompt_json",
            )
        return result

    async def _verify_once(
        self, config: ProviderRuntimeConfig, model: str
    ) -> ProviderModelVerificationResult:
        client = self._client_builder(config, model)
        try:
            result = await client.chat_structured(
                [
                    {
                        "role": "user",
                        "content": "Return a JSON object whose status is OK.",
                    }
                ],
                {
                    "type": "object",
                    "properties": {"status": {"type": "string"}},
                    "required": ["status"],
                    "additionalProperties": False,
                },
                max_tokens=256,
                max_retries=1,
                schema_name="provider_model_probe",
            )
            if not isinstance(result, dict) or not str(result.get("status", "")).strip():
                raise ValueError("structured probe response is invalid")
            return ProviderModelVerificationResult(
                model=model,
                status="verified",
                message="结构化验证成功",
            )
        except Exception as error:  # noqa: BLE001 - adapters expose multiple SDK errors
            classified = _classify_exception(error)
            return ProviderModelVerificationResult(
                model=model,
                status=("temporary_error" if classified.retryable else "unavailable"),
                message=classified.message,
                error_code=classified.code,
            )


class ProviderClientResolver:
    def __init__(
        self,
        *,
        repository: ProviderConfigurationRepository,
        crypto: ProviderCrypto,
        legacy_settings=None,
        client_builder: Callable[[ProviderRuntimeConfig, str], Any] = _default_client_builder,
        group_scoped: bool = False,
    ) -> None:
        if legacy_settings is None:
            from app.core.config import settings as current_settings

            legacy_settings = current_settings
        self._repository = repository
        self._crypto = crypto
        self._legacy = legacy_settings
        self._client_builder = client_builder
        # A group-scoped resolver must resolve ONLY against the group's own
        # provider rows; falling back to legacy env keys would leak credentials
        # across groups, so it raises instead.
        self._group_scoped = group_scoped

    async def primary(self, slug: str, model: str | None):
        resolved = await self.resolve_primary(slug, model)
        return resolved.client

    async def resolve_primary(
        self, slug: str, model: str | None
    ) -> ResolvedProviderClient:
        config = await self._load(slug)
        selected_model = model or config.default_model
        if config.supported_models and selected_model not in config.supported_models:
            raise ProviderResolutionError(
                code="PROVIDER_MODEL_INVALID",
                message="The selected model is not available for this provider",
            )
        if config.slug == "custom" and config.api_protocol == "openai":
            validation = await self._repository.get_model_validation(
                config.slug,
                config.api_protocol,
                selected_model,
            )
            if (
                validation is None
                or validation.status != "verified"
                or int(getattr(validation, "connection_revision", 1))
                != config.connection_revision
                or not getattr(validation, "transport_mode", None)
                or not getattr(validation, "structured_output_mode", None)
            ):
                raise ProviderResolutionError(
                    code="PROVIDER_MODEL_NOT_VERIFIED",
                    message=(
                        "The selected model must be verified for the current "
                        "custom OpenAI connection"
                    ),
                )
            config = replace(
                config,
                transport_mode=validation.transport_mode,
                structured_output_mode=validation.structured_output_mode,
            )
        return ResolvedProviderClient(
            client=self._client_builder(config, selected_model),
            provider=slug,
            model=selected_model,
        )

    async def resolve_secondary_deepseek(self) -> ResolvedProviderClient | None:
        try:
            config = await self._load("deepseek")
        except ProviderResolutionError as error:
            if error.code in {
                "PROVIDER_NOT_CONFIGURED",
                "PROVIDER_DISABLED",
                "PROVIDER_CONFIG_DECRYPT_FAILED",
            }:
                return None
            raise
        return ResolvedProviderClient(
            client=self._client_builder(config, config.default_model),
            provider="deepseek",
            model=config.default_model,
        )

    async def secondary_deepseek(self):
        resolved = await self.resolve_secondary_deepseek()
        return resolved.client if resolved else None

    async def is_available(self, slug: str) -> bool:
        try:
            await self._load(slug)
            return True
        except ProviderResolutionError:
            return False

    async def _load(self, slug: str) -> ProviderRuntimeConfig:
        if slug in RETIRED_PROVIDER_SLUGS:
            raise ProviderResolutionError(
                code="PROVIDER_RETIRED",
                message="该供应商已下线，请选择其他供应商",
                retryable=False,
            )
        record = await self._repository.get(slug)
        role: Literal["primary", "secondary"] = (
            "secondary" if slug == "deepseek" else "primary"
        )
        if record is not None:
            if not record.is_enabled:
                raise ProviderResolutionError(
                    code="PROVIDER_DISABLED",
                    message="The selected provider is disabled",
                )
            if not record.encrypted_api_key:
                raise ProviderResolutionError(
                    code="PROVIDER_NOT_CONFIGURED",
                    message="The selected provider has no API key",
                )
            try:
                api_key = self._crypto.decrypt(record.encrypted_api_key)
            except ProviderDecryptionError as error:
                raise ProviderResolutionError(
                    code="PROVIDER_CONFIG_DECRYPT_FAILED",
                    message="The API key must be re-entered",
                ) from error
            return ProviderRuntimeConfig(
                slug=slug,
                provider_type=record.provider_type,
                api_protocol=getattr(record, "api_protocol", "openai"),
                display_name=record.display_name,
                role=role,
                base_url=record.base_url,
                default_model=record.default_model,
                api_key=api_key,
                supported_models=tuple(
                    getattr(record, "supported_models", []) or []
                ),
                connection_revision=int(
                    getattr(record, "validation_revision", 1)
                ),
            )

        if self._group_scoped:
            raise ProviderResolutionError(
                code="PROVIDER_NOT_CONFIGURED",
                message="The selected provider is not configured for your API group",
            )
        if slug == "custom":
            raise ProviderResolutionError(
                code="PROVIDER_NOT_CONFIGURED",
                message="The custom provider is not configured",
            )
        if slug == "cattoken_claude":
            raise ProviderResolutionError(
                code="PROVIDER_NOT_CONFIGURED",
                message="The selected provider is not configured",
            )
        api_key = getattr(self._legacy, f"{slug}_api_key", "")
        if not api_key:
            raise ProviderResolutionError(
                code="PROVIDER_NOT_CONFIGURED",
                message="The selected provider is not configured",
            )
        defaults = {
            "openai": ("openai", "OpenAI", None, "gpt-4o"),
            "cattoken": (
                "openai_compatible",
                "CatToken",
                "https://www.cattoken.vip/v1",
                "gpt-5.4",
            ),
            "deepseek": (
                "openai_compatible",
                "DeepSeek",
                "https://api.deepseek.com",
                "deepseek-chat",
            ),
        }
        provider_type, name, default_url, default_model = defaults[slug]
        return ProviderRuntimeConfig(
            slug=slug,
            provider_type=provider_type,
            display_name=name,
            role=role,
            base_url=getattr(self._legacy, f"{slug}_base_url", default_url),
            default_model=getattr(self._legacy, f"{slug}_model", default_model),
            api_key=api_key,
        )


__all__ = [
    "ProviderClientResolver",
    "ProviderConnectionError",
    "ProviderConnectionTestResult",
    "ProviderConnectionTester",
    "ProviderErrorClassification",
    "ProviderModelVerificationResult",
    "ProviderModelVerifier",
    "ProviderResolutionError",
    "ProviderRuntimeConfig",
    "ResolvedProviderClient",
    "classify_provider_error",
]
