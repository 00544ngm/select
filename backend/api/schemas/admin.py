from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from backend.api.schemas.auth import UserRole, UserStatus


class ApiGroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    note: str | None = Field(None, max_length=500)
    base_url: str | None = Field(None, max_length=500)
    api_key: SecretStr | None = None
    default_model: str | None = Field(None, max_length=120)
    supported_models: list[str] = Field(default_factory=list)


class ApiGroupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=80)
    status: UserStatus | None = None
    note: str | None = Field(None, max_length=500)
    base_url: str | None = Field(None, max_length=500)
    api_key: SecretStr | None = None
    clear_api_key: bool = False
    default_model: str | None = Field(None, max_length=120)
    supported_models: list[str] | None = None

    @model_validator(mode="after")
    def validate_key_action(self) -> ApiGroupUpdate:
        if self.api_key is not None and self.clear_api_key:
            raise ValueError("api_key 与 clear_api_key 不能同时使用")
        return self


class ApiGroupPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: UserStatus
    note: str | None = None
    base_url: str | None = None
    masked_api_key: str | None = None
    default_model: str | None = None
    supported_models: list[str] = Field(default_factory=list)
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    full_name: str | None = Field(None, max_length=80)
    role: UserRole = "employee"
    status: UserStatus = "active"
    api_group_id: str | None = None


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(None, max_length=80)
    role: UserRole | None = None
    status: UserStatus | None = None
    api_group_id: str | None = None


class AdminUserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: UserRole
    status: UserStatus
    full_name: str | None = None
    api_group_id: str | None = None
    must_change_password: bool = False
    created_at: datetime
    updated_at: datetime


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=6, max_length=128)


__all__ = [
    "AdminUserPublic",
    "ApiGroupCreate",
    "ApiGroupPublic",
    "ApiGroupUpdate",
    "ResetPasswordRequest",
    "UserCreate",
    "UserUpdate",
]
