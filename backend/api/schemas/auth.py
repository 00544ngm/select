from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

UserRole = Literal["admin", "employee"]
UserStatus = Literal["active", "disabled"]


class UserPublic(BaseModel):
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


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class MeResponse(BaseModel):
    user: UserPublic


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str | None = Field(None, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


__all__ = [
    "ChangePasswordRequest",
    "LoginRequest",
    "LoginResponse",
    "MeResponse",
    "UserPublic",
    "UserRole",
    "UserStatus",
]
