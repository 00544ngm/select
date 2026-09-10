from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.exceptions import UnsupportedPlatformError
from app.domain.product_url import detect_product_platform

JobMode = Literal["hypothesis", "judgment", "batch"]
JobStatus = Literal["queued", "running", "completed", "failed", "interrupted"]
TaskProvider = Literal["openai", "custom", "claude"]


class RotationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: TaskProvider
    model: str = Field(min_length=1, max_length=120)
    api_protocol: Literal["openai", "anthropic"] = "openai"
    connection_revision: int = Field(default=1, ge=1)


class RotationRequestFields(BaseModel):
    rotation_enabled: bool = False
    rotation_candidates: list[RotationCandidate] | None = None

    @model_validator(mode="after")
    def validate_rotation_candidates(self) -> RotationRequestFields:
        if self.rotation_enabled and not self.rotation_candidates:
            raise ValueError("rotation_candidates are required when rotation is enabled")
        return self


class CrossReviewModel(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=120)


class CrossReviewCreate(BaseModel):
    reviewer_a: CrossReviewModel
    reviewer_b: CrossReviewModel


class JobNameUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


def _validated_url(value: str) -> str:
    normalized = value.strip()
    try:
        detect_product_platform(normalized)
    except UnsupportedPlatformError as error:
        raise ValueError(str(error)) from error
    return normalized


class HypothesisJobCreate(RotationRequestFields):
    name: str | None = None
    url: str
    model: str | None = None
    provider: TaskProvider | None = None

    _validate_url = field_validator("url")(_validated_url)


class JudgmentJobCreate(RotationRequestFields):
    name: str | None = None
    a_url: str
    b_urls: list[str] = Field(min_length=1, max_length=50)
    model: str | None = None
    provider: TaskProvider | None = None

    _validate_a_url = field_validator("a_url")(_validated_url)

    @field_validator("b_urls")
    @classmethod
    def validate_b_urls(cls, values: list[str]) -> list[str]:
        return [_validated_url(value) for value in values]


class BatchJobCreate(RotationRequestFields):
    name: str | None = None
    urls: list[str] = Field(min_length=1, max_length=500)
    model: str | None = None
    provider: TaskProvider | None = None

    @field_validator("urls")
    @classmethod
    def validate_and_deduplicate_urls(cls, values: list[str]) -> list[str]:
        unique_urls: dict[str, None] = {}
        for value in values:
            unique_urls[_validated_url(value)] = None
        return list(unique_urls)


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None = None
    mode: JobMode
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    error_code: str | None = None
    error_message: str | None = None
    retry_of_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    # Result highlights for list views (populated from result_payload when available)
    grade: str | None = None
    score: float | None = None
    product_title: str | None = None
    product_title_zh: str | None = None
    product_id: str | None = None
    product_image: str | None = None
    top_direction_name: str | None = None
    top_direction_keywords: dict[str, str] = Field(default_factory=dict)
    top_direction_score: float | None = None
    top_direction_type: str | None = None
    provider: str | None = None
    provider_model: str | None = None
    rotation_enabled: bool = False
    attempt_count: int = Field(default=0, ge=0)
    successful_model: str | None = None


class JobAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ordinal: int = Field(ge=1)
    provider: str
    api_protocol: Literal["openai", "anthropic"]
    model: str
    status: Literal["running", "succeeded", "failed"]
    stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class JobRotationSnapshot(BaseModel):
    enabled: bool = False
    candidates: list[RotationCandidate] = Field(default_factory=list)
    snapshot_version: int | None = None


class JobDetail(JobSummary):
    request_payload: dict[str, Any]
    result_payload: dict[str, Any] | None = None
    rotation: JobRotationSnapshot | None = None
    attempts: list[JobAttemptResponse] = Field(default_factory=list)


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: Literal["json", "excel"]
    size: int = Field(ge=0)
    checksum: str
    created_at: datetime


class JobListResponse(BaseModel):
    items: list[JobSummary]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


__all__ = [
    "ArtifactResponse",
    "BatchJobCreate",
    "CrossReviewCreate",
    "CrossReviewModel",
    "HypothesisJobCreate",
    "JobAttemptResponse",
    "JobDetail",
    "JobListResponse",
    "JobMode",
    "JobNameUpdate",
    "JobRotationSnapshot",
    "JobStatus",
    "JobSummary",
    "JudgmentJobCreate",
    "RotationCandidate",
    "RotationRequestFields",
]
