from __future__ import annotations

import asyncio
import inspect
import json
import random
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import anthropic
from anthropic import AsyncAnthropic

from app.core.config import settings
from app.core.exceptions import LLMError
from app.domain.interfaces import LLMClient as LLMClientInterface


class AnthropicLLMError(LLMError):
    """Redacted Anthropic failure with stable worker-facing metadata."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(message)


def normalize_anthropic_base_url(base_url: str) -> str:
    """Return the SDK base URL for an Anthropic Messages endpoint."""
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Anthropic base URL must use http or https")

    path = parsed.path.rstrip("/")
    for suffix in ("/v1/messages", "/v1"):
        if path.lower().endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _retry_after_seconds(error: Exception) -> float | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    value = headers.get("retry-after")
    try:
        return max(0.0, min(float(value), 60.0))
    except (TypeError, ValueError):
        return None


def _classify_anthropic_error(error: Exception) -> AnthropicLLMError:
    if isinstance(error, AnthropicLLMError):
        return error
    if isinstance(error, ValueError):
        message = str(error)
        return AnthropicLLMError(
            code=(
                "PROVIDER_EMPTY_RESPONSE"
                if "empty response" in message.lower()
                else "MODEL_INVALID_JSON"
            ),
            message=message,
            retryable=True,
        )
    if isinstance(error, anthropic.APITimeoutError):
        return AnthropicLLMError(
            code="PROVIDER_MODEL_TASK_TIMEOUT",
            message="Anthropic model request timed out",
            retryable=True,
        )
    if isinstance(error, anthropic.APIConnectionError):
        return AnthropicLLMError(
            code="PROVIDER_CONNECTION_FAILED",
            message="Unable to connect to the Anthropic-compatible service",
            retryable=True,
        )

    status_code = getattr(error, "status_code", None)
    retry_after = _retry_after_seconds(error)
    status_errors: dict[int, tuple[str, str, bool]] = {
        400: (
            "PROVIDER_PROTOCOL_MISMATCH",
            "The service did not accept an Anthropic Messages API request",
            False,
        ),
        401: ("PROVIDER_AUTH_FAILED", "The API Key is invalid", False),
        403: (
            "PROVIDER_PERMISSION_DENIED",
            "The API Key cannot access this model",
            False,
        ),
        404: (
            "PROVIDER_MODEL_INVALID",
            "The configured model was not found or is unavailable",
            False,
        ),
        413: (
            "PROVIDER_REQUEST_TOO_LARGE",
            "The Anthropic-compatible service rejected the request as too large",
            False,
        ),
        429: (
            "PROVIDER_RATE_LIMITED",
            "The Anthropic-compatible service is rate limited",
            True,
        ),
    }
    if isinstance(status_code, int) and status_code in status_errors:
        code, message, retryable = status_errors[status_code]
        return AnthropicLLMError(
            code=code,
            message=message,
            retryable=retryable,
            status_code=status_code,
            retry_after=retry_after,
        )
    if isinstance(status_code, int) and status_code >= 500:
        return AnthropicLLMError(
            code="PROVIDER_UPSTREAM_UNAVAILABLE",
            message="The Anthropic-compatible service is temporarily unavailable",
            retryable=True,
            status_code=status_code,
            retry_after=retry_after,
        )
    return AnthropicLLMError(
        code="PROVIDER_UPSTREAM_UNAVAILABLE",
        message="The Anthropic-compatible request failed temporarily",
        retryable=True,
        status_code=status_code if isinstance(status_code, int) else None,
        retry_after=retry_after,
    )


def _retry_delay(error: AnthropicLLMError, attempt: int) -> float:
    if error.retry_after is not None:
        return error.retry_after
    return min(2 ** (attempt - 1), 30) * random.uniform(0.8, 1.2)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
        elif isinstance(block, str):
            parts.append(block)
    return "".join(parts)


def _normalize_messages(messages: list[dict]) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    normalized: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            text = _content_text(message.get("content", "")).strip()
            if text:
                system_parts.append(text)
            continue
        if role in {"user", "assistant"}:
            normalized.append(
                {"role": role, "content": message.get("content", "")}
            )
    return "\n\n".join(system_parts), normalized


def _response_text(response: Any) -> str:
    return "".join(
        str(getattr(block, "text", ""))
        for block in getattr(response, "content", [])
        if getattr(block, "type", None) == "text"
    )


def _parse_json(text: str) -> Any:
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


def _parse_structured_response(response: Any) -> Any:
    try:
        return _parse_json(_response_text(response))
    except ValueError as error:
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "max_tokens":
            raise ValueError(
                f"response truncated (stop_reason=max_tokens): {error}"
            ) from error
        raise


def _compact_output_instruction(output_schema: dict[str, Any]) -> str:
    properties = output_schema.get("properties", {})
    direction_constraint = (
        " while preserving every required field and 8-10 directions"
        if isinstance(properties, dict) and "directions" in properties
        else " while preserving every required field"
    )
    return (
        f"Keep the JSON compact{direction_constraint}. Use short phrases, not "
        "paragraphs. Each ordinary text value must be at most 45 Chinese "
        "characters; each launch_actions array must contain at most 2 short "
        "items. Do not repeat evidence or explanations across fields."
    )


class AnthropicLLMClient(LLMClientInterface):
    """Anthropic Messages API adapter for custom providers."""

    def __init__(
        self,
        model: str,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout: float = 120.0,
        client_factory: Callable[..., Any] = AsyncAnthropic,
    ) -> None:
        if not api_key:
            raise LLMError("Anthropic API key is not configured")
        client_args: dict[str, Any] = {
            "api_key": api_key,
            "timeout": timeout,
            "max_retries": 0,
        }
        if base_url:
            client_args["base_url"] = normalize_anthropic_base_url(base_url)
        self._client_or_awaitable = client_factory(**client_args)
        self._client = None
        self._model = model

    async def _get_client(self):
        if self._client is None:
            client = self._client_or_awaitable
            if inspect.isawaitable(client):
                client = await client
            self._client = client
        return self._client

    async def chat(self, messages: list[dict], **kwargs: Any) -> str:
        max_retries = kwargs.pop("max_retries", settings.max_retries)
        model = kwargs.pop("model", self._model)
        max_tokens = kwargs.pop("max_tokens", settings.openai_max_tokens)
        kwargs.pop("schema_name", None)
        temperature = kwargs.pop("temperature", None)
        system_text, anthropic_messages = _normalize_messages(messages)
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
            **kwargs,
        }
        if system_text:
            request["system"] = system_text
        if temperature is not None:
            request["temperature"] = temperature

        total_attempts = max(1, int(max_retries))
        last_error: AnthropicLLMError | None = None
        last_cause: Exception | None = None
        for attempt in range(1, total_attempts + 1):
            try:
                client = await self._get_client()
                text = _response_text(await client.messages.create(**request))
                if not text.strip():
                    raise ValueError("empty response")
                return text
            except Exception as error:
                last_cause = error
                last_error = _classify_anthropic_error(error)
                if not last_error.retryable or attempt >= total_attempts:
                    break
                await asyncio.sleep(_retry_delay(last_error, attempt))
        assert last_error is not None
        raise last_error from last_cause

    async def chat_structured(
        self, messages: list[dict], output_schema: dict, **kwargs: Any
    ) -> Any:
        max_retries = kwargs.pop("max_retries", settings.max_retries)
        model = kwargs.pop("model", self._model)
        max_tokens = kwargs.pop("max_tokens", settings.openai_max_tokens)
        kwargs.pop("schema_name", None)
        temperature = kwargs.pop("temperature", None)
        system_text, anthropic_messages = _normalize_messages(messages)
        schema_instruction = (
            "Return only one valid JSON object matching this JSON Schema. "
            "Do not include Markdown or explanatory text:\n"
            f"{json.dumps(output_schema, ensure_ascii=False)}\n\n"
            f"{_compact_output_instruction(output_schema)}"
        )
        combined_system = "\n\n".join(
            part for part in (system_text, schema_instruction) if part
        )
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": combined_system,
            "messages": anthropic_messages,
            **kwargs,
        }
        if temperature is not None:
            request["temperature"] = temperature

        total_attempts = max(1, int(max_retries))
        last_error: AnthropicLLMError | None = None
        last_cause: Exception | None = None
        for attempt in range(1, total_attempts + 1):
            try:
                client = await self._get_client()
                async with client.messages.stream(**request) as stream:
                    response = await stream.get_final_message()
                return _parse_structured_response(response)
            except Exception as error:
                last_cause = error
                last_error = _classify_anthropic_error(error)
                if not last_error.retryable or attempt >= total_attempts:
                    break
                await asyncio.sleep(_retry_delay(last_error, attempt))
        assert last_error is not None
        raise last_error from last_cause


__all__ = [
    "AnthropicLLMClient",
    "AnthropicLLMError",
    "normalize_anthropic_base_url",
]
