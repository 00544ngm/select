from __future__ import annotations

import asyncio
import json
import random
from typing import Any

from openai import APITimeoutError, AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import LLMError, LLMTaskTimeoutError
from app.core.logger import logger
from app.domain.interfaces import LLMClient as LLMClientInterface
from app.infrastructure.llm.openai_compat import (
    OpenAIStructuredOutputMode,
    OpenAITransportMode,
    classify_openai_compatible_error,
)

_MODELS_USE_COMPLETION_TOKENS = {"o1", "o3", "o4"}
_MODELS_USE_COMPLETION_TOKENS_PREFIX = ("gpt-5.",)
_MODELS_NO_TEMPERATURE = _MODELS_USE_COMPLETION_TOKENS | {"gpt-5.5", "gpt-5.5-pro"}
_MODELS_NO_TEMPERATURE_PREFIX = ()

_DEFAULT_STRUCTURED_REPORT_TIMEOUT_SECONDS = 120.0
_SLOW_STRUCTURED_REPORT_TIMEOUT_SECONDS = 600.0
# 慢速结构化报告模型家族：前缀匹配（含 "-" 子型号）。gpt-5.5 与 gpt-5.6
# 同样产出大型 JSON（见 _LARGE_STRUCTURED_OUTPUT_MODELS），单次完整报告需要
# 远高于默认 120s 的预算，否则会在真实长请求上提前超时。
_SLOW_STRUCTURED_REPORT_MODELS = ("gpt-5.5", "gpt-5.6")
_LARGE_STRUCTURED_OUTPUT_MODELS = ("gpt-5.5", "gpt-5.6")
_LARGE_STRUCTURED_OUTPUT_TOKENS = 32768
_DEEPSEEK_LARGE_STRUCTURED_OUTPUT_MODELS = ("deepseek-v4",)
_DEEPSEEK_STRUCTURED_OUTPUT_TOKENS = 65536


def report_timeout_seconds(model: str, protocol: str = "openai") -> float:
    """Return the per-model deadline for one complete structured report."""
    del protocol  # protocol-specific clients may override this policy later
    normalized = model.strip().lower()
    for prefix in _SLOW_STRUCTURED_REPORT_MODELS:
        if normalized == prefix or normalized.startswith(f"{prefix}-"):
            return _SLOW_STRUCTURED_REPORT_TIMEOUT_SECONDS
    return _DEFAULT_STRUCTURED_REPORT_TIMEOUT_SECONDS


def supports_structured_report(model: str, protocol: str = "openai") -> bool:
    """Return whether the configured protocol has a structured-report path."""
    return bool(model.strip()) and protocol in {"openai", "anthropic"}


def _structured_output_max_tokens(model: str, configured: int) -> int:
    """Give reasoning report paths room to finish large JSON payloads.

    DeepSeek v4 reasoning models burn a large share of the output budget on
    hidden chain-of-thought, so they need a higher ceiling than the GPT paths.
    """
    normalized = model.strip().lower()
    if any(
        normalized == prefix or normalized.startswith(f"{prefix}-")
        for prefix in _DEEPSEEK_LARGE_STRUCTURED_OUTPUT_MODELS
    ):
        return max(configured, _DEEPSEEK_STRUCTURED_OUTPUT_TOKENS)
    if any(
        normalized == prefix or normalized.startswith(f"{prefix}-")
        for prefix in _LARGE_STRUCTURED_OUTPUT_MODELS
    ):
        return max(configured, _LARGE_STRUCTURED_OUTPUT_TOKENS)
    return configured


# Backward-compatible name used by the existing client tests and integrations.
def _structured_report_timeout_seconds(model: str) -> float:
    return report_timeout_seconds(model)


def _uses_responses_api(model: str) -> bool:
    return model.startswith("gpt-5.") or model in {"gpt-5.5", "gpt-5.5-pro"}


def _token_param(model: str, default: int) -> dict[str, int]:
    if model in _MODELS_USE_COMPLETION_TOKENS or model.startswith(_MODELS_USE_COMPLETION_TOKENS_PREFIX):
        return {"max_completion_tokens": default}
    return {"max_tokens": default}


def _temperature_param(model: str, default: float | None) -> dict[str, float]:
    if model in _MODELS_NO_TEMPERATURE or model.startswith(_MODELS_NO_TEMPERATURE_PREFIX):
        return {}
    if default is not None:
        return {"temperature": default}
    return {}


def _parse_structured_json(text: str) -> Any:
    """Parse a JSON response while allowing a surrounding Markdown code fence."""
    normalized = text.strip()
    if not normalized:
        raise ValueError("empty response")
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        normalized = "\n".join(lines).strip()
    try:
        return json.loads(normalized)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON: {error.msg}") from error


def _response_output_text(response: Any) -> str:
    status = getattr(response, "status", None)
    if status == "incomplete":
        details = getattr(response, "incomplete_details", None)
        reason = getattr(details, "reason", None) or "unknown"
        raise ValueError(f"response truncated: {reason}")
    return response.output_text or ""


def _openai_response_text(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as error:
        raise ValueError(
            "OpenAI-compatible response shape invalid: expected "
            "choices[0].message.content"
        ) from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            "OpenAI-compatible response shape invalid: response text is empty"
        )
    return content


def _is_openai_strict_schema(schema: Any) -> bool:
    """Return whether a schema satisfies OpenAI strict-mode object rules."""
    if isinstance(schema, list):
        return all(_is_openai_strict_schema(item) for item in schema)
    if not isinstance(schema, dict):
        return True
    if schema.get("type") == "object":
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is not False:
            return False
        if set(schema.get("required", [])) != set(properties):
            return False
    return all(_is_openai_strict_schema(value) for value in schema.values())


class OpenAILLMClient(LLMClientInterface):
    """GPT client using OpenAI API. Supports chat and structured output."""

    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        transport_mode: OpenAITransportMode | None = None,
        structured_output_mode: OpenAIStructuredOutputMode | None = None,
    ) -> None:
        resolved_key = api_key or settings.openai_api_key
        if not resolved_key:
            raise LLMError("OPENAI_API_KEY is not configured")
        client_args: dict[str, Any] = {
            "api_key": resolved_key,
            "timeout": 120.0,
            "max_retries": 0,
        }
        if base_url:
            client_args["base_url"] = base_url
        self._client = AsyncOpenAI(**client_args)
        self._model = model or settings.openai_model
        self._transport_mode = transport_mode
        self._structured_output_mode = structured_output_mode

    def _uses_responses(self, model: str) -> bool:
        if self._transport_mode is not None:
            return self._transport_mode == "responses"
        return _uses_responses_api(model)

    async def chat(self, messages: list[dict], **kwargs: Any) -> str:
        max_retries = kwargs.pop("max_retries", settings.max_retries)
        model = kwargs.pop("model", self._model)
        temperature = kwargs.pop("temperature", settings.openai_temperature)
        max_tokens = kwargs.pop("max_tokens", settings.openai_max_tokens)
        token_param = _token_param(model, max_tokens)
        temp_param = _temperature_param(model, temperature)
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                if self._uses_responses(model):
                    response = await self._client.responses.create(
                        model=model,
                        input=messages,
                        max_output_tokens=max_tokens,
                        **kwargs,
                    )
                    return response.output_text or ""
                resp = await self._client.chat.completions.create(
                    model=model, messages=messages,
                    **temp_param, **token_param, **kwargs)
                return resp.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001 - SDK adapters expose varied errors
                last_error = (
                    classify_openai_compatible_error(e)
                    if self._transport_mode is not None
                    else e
                )
                if (
                    attempt < max_retries
                    and getattr(last_error, "retryable", True)
                ):
                    await asyncio.sleep(attempt * random.uniform(1, 3))
                elif not getattr(last_error, "retryable", True):
                    break
        raise LLMError(f"GPT chat failed after {max_retries} attempts") from last_error

    async def chat_structured(self, messages, output_schema, **kwargs):
        max_retries = kwargs.pop("max_retries", settings.max_retries)
        model = kwargs.pop("model", self._model)
        schema_name = kwargs.pop("schema_name", "structured_output")
        temperature = kwargs.pop("temperature", settings.openai_temperature)
        explicit_max_tokens = kwargs.pop("max_tokens", None)
        max_tokens = (
            _structured_output_max_tokens(model, settings.openai_max_tokens)
            if explicit_max_tokens is None
            else explicit_max_tokens
        )
        request_timeout = report_timeout_seconds(model, "openai")
        token_param = _token_param(model, max_tokens)
        temp_param = _temperature_param(model, temperature)
        structured_output_mode = self._structured_output_mode
        if structured_output_mode is None:
            structured_output_mode = (
                "json_schema"
                if _is_openai_strict_schema(output_schema)
                else "json_object"
            )
        elif (
            structured_output_mode == "json_schema"
            and not _is_openai_strict_schema(output_schema)
        ):
            # Schema does not satisfy OpenAI strict-mode rules (every object
            # level must close additionalProperties=false). Providers enforcing
            # strict json_schema (OpenAI official or maike relay) reject it with
            # 400. Degrade to json_object, which embeds the schema in the prompt
            # and does not require a strict-compliant schema.
            structured_output_mode = "json_object"
        schema_json = json.dumps(output_schema, ensure_ascii=False)
        compatibility_messages = [
            {
                "role": "system",
                "content": (
                    "Return only one valid JSON object matching this JSON Schema. "
                    "Do not include Markdown or explanatory text:\n"
                    f"{schema_json}"
                ),
            },
            *messages,
        ]
        if structured_output_mode == "json_schema":
            request_messages = messages
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": output_schema,
                },
            }
        elif structured_output_mode == "json_object":
            request_messages = compatibility_messages
            response_format = {"type": "json_object"}
        else:
            request_messages = compatibility_messages
            response_format = None
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                if self._uses_responses(model):
                    response = await self._client.responses.create(
                        model=model,
                        input=compatibility_messages,
                        max_output_tokens=max_tokens,
                        timeout=request_timeout,
                        **kwargs,
                    )
                    return _parse_structured_json(_response_output_text(response))
                request_args = {
                    "model": model,
                    "messages": request_messages,
                    **temp_param,
                    **token_param,
                    "timeout": request_timeout,
                    **kwargs,
                }
                if response_format is not None:
                    request_args["response_format"] = response_format
                resp = await self._client.chat.completions.create(**request_args)
                text = _openai_response_text(resp)
                return _parse_structured_json(text)
            except Exception as e:  # noqa: BLE001 - SDK adapters expose varied errors
                last_error = (
                    classify_openai_compatible_error(e)
                    if self._transport_mode is not None
                    else e
                )
                if (
                    attempt < max_retries
                    and getattr(last_error, "retryable", True)
                ):
                    await asyncio.sleep(attempt * random.uniform(1, 3))
                elif not getattr(last_error, "retryable", True):
                    break
        if (
            self._transport_mode is not None
            and last_error is not None
            and hasattr(last_error, "code")
        ):
            raise last_error
        if isinstance(last_error, APITimeoutError) or (
            last_error is not None and "timed out" in str(last_error).lower()
        ):
            raise LLMTaskTimeoutError(
                model=model,
                timeout_seconds=int(request_timeout),
            ) from last_error
        reason = str(last_error) if last_error else "unknown error"
        raise LLMError(f"GPT structured output failed: {reason}") from last_error




class DeepSeekLLMClient(LLMClientInterface):
    """DeepSeek LLM client using OpenAI-compatible API."""

    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        resolved_key = api_key or settings.deepseek_api_key
        if not resolved_key:
            raise LLMError("DEEPSEEK_API_KEY is not configured")
        self._client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=base_url or settings.deepseek_base_url,
        )
        self._model = model or settings.deepseek_model

    async def chat(self, messages: list[dict], **kwargs: Any) -> str:
        max_retries = kwargs.pop("max_retries", settings.max_retries)
        model = kwargs.pop("model", self._model)
        temperature = kwargs.pop("temperature", 0.3)
        explicit_max_tokens = kwargs.pop("max_tokens", None)
        max_tokens = (
            _structured_output_max_tokens(model, settings.openai_max_tokens)
            if explicit_max_tokens is None
            else explicit_max_tokens
        )
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = await self._client.chat.completions.create(
                    model=model, messages=messages,
                    temperature=temperature, max_tokens=max_tokens, **kwargs)
                return resp.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001 - SDK adapters expose varied errors
                last_error = e
                if attempt < max_retries:
                    await asyncio.sleep(attempt * random.uniform(1, 3))
        raise LLMError(f"DeepSeek chat failed after {max_retries} attempts") from last_error

    async def chat_structured(self, messages, output_schema, **kwargs):
        max_retries = kwargs.pop("max_retries", settings.max_retries)
        model = kwargs.pop("model", self._model)
        kwargs.pop("schema_name", None)
        temperature = kwargs.pop("temperature", 0.3)
        explicit_max_tokens = kwargs.pop("max_tokens", None)
        max_tokens = (
            _structured_output_max_tokens(model, settings.openai_max_tokens)
            if explicit_max_tokens is None
            else explicit_max_tokens
        )
        schema_json = json.dumps(output_schema, ensure_ascii=False)
        # DeepSeek doesn't support native response_format: json_schema,
        # so we use chat() with a JSON instruction prompt.
        json_instruction = {
            "role": "system",
            "content": f"你必须以 JSON 格式输出，严格遵循以下 schema：\n{schema_json}\n只输出 JSON，不要包含其他内容。",
        }
        chat_messages = [json_instruction] + list(messages)
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = await self._client.chat.completions.create(
                    model=model, messages=chat_messages,
                    temperature=temperature, max_tokens=max_tokens,
                    **kwargs,
                )
                text = resp.choices[0].message.content or "{}"
                # Strip markdown code fences if present
                text = text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1]
                    text = text.rsplit("```", 1)[0]
                return json.loads(text)
            except Exception as e:  # noqa: BLE001 - SDK adapters expose varied errors
                last_error = e
                if attempt < max_retries:
                    await asyncio.sleep(attempt * random.uniform(1, 3))
        raise LLMError("DeepSeek structured output failed") from last_error



class CatTokenLLMClient(LLMClientInterface):
    """CatToken API client (OpenAI-compatible proxy for gpt-5.4/5.5/5.6 series)."""

    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        resolved_key = api_key or settings.cattoken_api_key
        if not resolved_key:
            raise LLMError("CATTOKEN_API_KEY is not configured")
        self._client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=base_url or settings.cattoken_base_url,
        )
        self._model = model or settings.cattoken_model

    async def chat(self, messages: list[dict], **kwargs: Any) -> str:
        max_retries = kwargs.pop("max_retries", settings.max_retries)
        model = kwargs.pop("model", self._model)
        kwargs.pop("temperature", None)
        max_tokens = kwargs.pop("max_tokens", settings.openai_max_tokens)
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                response = await self._client.responses.create(
                    model=model,
                    input=messages,
                    max_output_tokens=max_tokens,
                    **kwargs,
                )
                return response.output_text or ""
            except Exception as e:  # noqa: BLE001 - SDK adapters expose varied errors
                last_error = e
                if attempt < max_retries:
                    await asyncio.sleep(attempt * random.uniform(1, 3))
        raise LLMError(f"CatToken chat failed after {max_retries} attempts") from last_error

    async def chat_structured(self, messages, output_schema, **kwargs):
        max_retries = kwargs.pop("max_retries", settings.max_retries)
        model = kwargs.pop("model", self._model)
        kwargs.pop("schema_name", None)
        kwargs.pop("temperature", None)
        max_tokens = kwargs.pop("max_tokens", settings.openai_max_tokens)
        schema_json = json.dumps(output_schema, ensure_ascii=False)
        compatibility_messages = [
            {
                "role": "system",
                "content": (
                    "Return only one valid JSON object matching this JSON Schema. "
                    f"Do not include Markdown or explanatory text:\n{schema_json}"
                ),
            },
            *messages,
        ]
        last_error = None
        for attempt in range(1, max_retries + 1):
            response = None
            try:
                response = await self._client.responses.create(
                    model=model,
                    input=compatibility_messages,
                    max_output_tokens=max_tokens,
                    **kwargs,
                )
                text = response.output_text or ""
                return _parse_structured_json(text)
            except Exception as error:  # noqa: BLE001 - SDK adapters expose varied errors
                last_error = error
                logger.warning(
                    "CatToken structured response failed: response_type={}, reason={}",
                    type(response).__name__ if response is not None else "unavailable",
                    str(error),
                )
                if attempt < max_retries:
                    await asyncio.sleep(attempt * random.uniform(1, 3))
        reason = str(last_error) if last_error else "unknown error"
        raise LLMError(f"CatToken structured output failed: {reason}") from last_error


from app.infrastructure.llm.anthropic_client import AnthropicLLMClient

__all__ = [
    "AnthropicLLMClient",
    "CatTokenLLMClient",
    "DeepSeekLLMClient",
    "OpenAILLMClient",
    "report_timeout_seconds",
    "supports_structured_report",
]
