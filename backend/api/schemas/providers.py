from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, model_validator

ProviderSlug = Literal["openai", "deepseek", "custom", "claude"]
ProviderApiProtocol = Literal["openai", "anthropic"]
ProviderRole = Literal["primary", "secondary"]
ProviderTestStatus = Literal["untested", "success", "failed"]
ProviderModelTestStatus = Literal[
    "discovered", "verified", "unavailable", "temporary_error", "expired"
]


class ProviderDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_protocol: ProviderApiProtocol = "openai"
    display_name: str | None = Field(None, min_length=1, max_length=80)
    base_url: HttpUrl | None = None
    default_model: str = Field(min_length=1, max_length=120)
    api_key: SecretStr | None = None


class ProviderUpdate(ProviderDraft):
    is_enabled: bool
    clear_api_key: bool = False

    @model_validator(mode="after")
    def validate_key_action(self) -> ProviderUpdate:
        if self.api_key is not None and self.clear_api_key:
            raise ValueError("api_key and clear_api_key cannot be used together")
        return self


class ProviderModelOption(BaseModel):
    provider: ProviderSlug
    provider_display_name: str
    api_protocol: ProviderApiProtocol
    model: str
    is_default: bool
    is_selected: bool = False
    is_enabled: bool
    test_status: ProviderModelTestStatus
    tested_at: datetime | None
    test_message: str | None
    error_code: str | None = None
    connection_revision: int = 1
    current_connection_revision: int = 1
    is_current_connection: bool = True
    last_used_at: datetime | None = None
    use_count: int = 0
    last_auto_tested_at: datetime | None = None
    transport_mode: Literal["chat_completions", "responses"] | None = None
    structured_output_mode: Literal[
        "json_schema", "json_object", "prompt_json"
    ] | None = None


class ProviderPublic(BaseModel):
    slug: ProviderSlug
    api_protocol: ProviderApiProtocol = "openai"
    display_name: str
    role: ProviderRole
    base_url: str | None
    default_model: str
    supported_models: list[str] = Field(default_factory=list)
    model_options: list[ProviderModelOption] = Field(default_factory=list)
    is_enabled: bool
    configured: bool
    masked_api_key: str | None
    last_test_status: ProviderTestStatus
    last_tested_at: datetime | None
    last_test_message: str | None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def ensure_model_options(self) -> ProviderPublic:
        if not self.model_options and self.supported_models:
            self.model_options = [
                ProviderModelOption(
                    provider=self.slug,
                    provider_display_name=self.display_name,
                    api_protocol=self.api_protocol,
                    model=model,
                    is_default=model == self.default_model,
                    is_selected=False,
                    is_enabled=self.is_enabled,
                    test_status="discovered",
                    tested_at=None,
                    test_message="目录发现，尚未真实验证",
                )
                for model in self.supported_models
            ]
        return self


class ProviderTestResult(BaseModel):
    status: Literal["success"] = "success"
    message: str
    models: list[str] = Field(default_factory=list)


class ProviderModelVerifyRequest(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    set_default: bool = True
    is_automatic: bool = False


class ProviderModelVerifyResult(BaseModel):
    provider: ProviderSlug
    model: str
    test_status: ProviderModelTestStatus
    tested_at: datetime
    test_message: str
    error_code: str | None = None
    is_default: bool = False
    transport_mode: Literal["chat_completions", "responses"] | None = None
    structured_output_mode: Literal[
        "json_schema", "json_object", "prompt_json"
    ] | None = None


class ProviderModelSelectionRequest(BaseModel):
    is_selected: bool


class ProviderModelSelectionResult(BaseModel):
    provider: ProviderSlug
    model: str
    is_selected: bool


__all__ = [
    "ProviderApiProtocol",
    "ProviderDraft",
    "ProviderModelOption",
    "ProviderModelSelectionRequest",
    "ProviderModelSelectionResult",
    "ProviderModelTestStatus",
    "ProviderModelVerifyRequest",
    "ProviderModelVerifyResult",
    "ProviderPublic",
    "ProviderRole",
    "ProviderSlug",
    "ProviderTestResult",
    "ProviderUpdate",
]
