from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from openai import APIConnectionError, APITimeoutError

from app.core.exceptions import LLMError

OpenAITransportMode = Literal["chat_completions", "responses"]
OpenAIStructuredOutputMode = Literal["json_schema", "json_object", "prompt_json"]


class OpenAICompatibleLLMError(LLMError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code
        super().__init__(message)


def classify_openai_compatible_error(error: Exception) -> OpenAICompatibleLLMError:
    if isinstance(error, OpenAICompatibleLLMError):
        return error
    if isinstance(error, APITimeoutError):
        return OpenAICompatibleLLMError(
            code="PROVIDER_MODEL_TASK_TIMEOUT",
            message="OpenAI-compatible model request timed out",
            retryable=True,
        )
    if isinstance(error, APIConnectionError):
        return OpenAICompatibleLLMError(
            code="PROVIDER_CONNECTION_FAILED",
            message="Unable to connect to the OpenAI-compatible service",
            retryable=True,
        )
    if isinstance(error, ValueError):
        normalized = str(error).lower()
        return OpenAICompatibleLLMError(
            code=(
                "PROVIDER_EMPTY_RESPONSE"
                if "empty" in normalized
                else "MODEL_INVALID_JSON"
            ),
            message=(
                "The OpenAI-compatible service returned an empty response"
                if "empty" in normalized
                else "The OpenAI-compatible service returned invalid JSON"
            ),
            retryable=True,
        )

    status_code = getattr(error, "status_code", None)
    normalized = str(error).lower()
    if status_code == 401:
        code, message, retryable = "PROVIDER_AUTH_FAILED", "The API Key is invalid", False
    elif status_code == 403:
        code, message, retryable = (
            "PROVIDER_PERMISSION_DENIED",
            "The API Key cannot access this model",
            False,
        )
    elif status_code in {404, 405}:
        endpoint_error = status_code == 405 or any(
            marker in normalized
            for marker in ("endpoint", "route", "url", "method not allowed")
        )
        code, message, retryable = (
            (
                "PROVIDER_PROTOCOL_MISMATCH",
                "The OpenAI-compatible endpoint is not supported",
                False,
            )
            if endpoint_error
            else (
                "PROVIDER_MODEL_INVALID",
                "The configured model was not found or is unavailable",
                False,
            )
        )
    elif status_code == 400 and "response_format" in normalized:
        code, message, retryable = (
            "PROVIDER_STRUCTURED_OUTPUT_UNSUPPORTED",
            "The provider does not support this structured output mode",
            False,
        )
    elif status_code == 400:
        code, message, retryable = (
            "PROVIDER_PROTOCOL_MISMATCH",
            "The provider rejected the OpenAI-compatible request",
            False,
        )
    elif status_code == 413:
        code, message, retryable = (
            "PROVIDER_REQUEST_TOO_LARGE",
            "The OpenAI-compatible request is too large",
            False,
        )
    elif status_code == 429:
        code, message, retryable = (
            "PROVIDER_RATE_LIMITED",
            "The OpenAI-compatible service is rate limited",
            True,
        )
    elif isinstance(status_code, int) and status_code >= 500:
        code, message, retryable = (
            "PROVIDER_UPSTREAM_UNAVAILABLE",
            "The OpenAI-compatible service is temporarily unavailable",
            True,
        )
    else:
        code, message, retryable = (
            "PROVIDER_UPSTREAM_UNAVAILABLE",
            "The OpenAI-compatible request failed temporarily",
            True,
        )
    return OpenAICompatibleLLMError(
        code=code,
        message=message,
        retryable=retryable,
        status_code=status_code if isinstance(status_code, int) else None,
    )


def normalize_openai_compatible_base_url(raw: str) -> str:
    parsed = urlsplit(raw.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("OpenAI-compatible base URL must use http or https")

    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if not path.endswith("/v1"):
        path = f"{path}/v1"

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


__all__ = [
    "OpenAICompatibleLLMError",
    "OpenAIStructuredOutputMode",
    "OpenAITransportMode",
    "classify_openai_compatible_error",
    "normalize_openai_compatible_base_url",
]
