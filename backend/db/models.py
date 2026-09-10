from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_analysis_jobs_status_created", "status", "created_at"),
        Index("ix_analysis_jobs_mode_created", "mode", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str | None] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    progress: Mapped[int] = mapped_column(default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_of_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"),
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class ProductSnapshot(Base):
    __tablename__ = "product_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    scraped_data: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )


class JobProduct(Base):
    __tablename__ = "job_products"
    __table_args__ = (UniqueConstraint("job_id", "role", "position"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("product_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(default=0, nullable=False)


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("job_id", "kind"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )


class JobModelAttempt(Base):
    __tablename__ = "job_model_attempts"
    __table_args__ = (
        UniqueConstraint("job_id", "ordinal"),
        Index("ix_job_model_attempts_job_ordinal", "job_id", "ordinal"),
        Index("ix_job_model_attempts_job_status", "job_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    api_protocol: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ProviderConfiguration(Base):
    __tablename__ = "provider_configurations"
    __table_args__ = (UniqueConstraint("slug"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    api_protocol: Mapped[str] = mapped_column(
        String(20), default="openai", nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    default_model: Mapped[str] = mapped_column(String(120), nullable=False)
    supported_models: Mapped[list[str]] = mapped_column(
        JSON_TYPE, default=list, nullable=False
    )
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    api_key_last4: Mapped[str | None] = mapped_column(String(4))
    is_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_test_status: Mapped[str] = mapped_column(
        String(16), default="untested", nullable=False
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_message: Mapped[str | None] = mapped_column(String(255))
    validation_revision: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class LocalQueueItem(Base):
    __tablename__ = "local_queue_items"
    __table_args__ = (Index("ix_local_queue_items_status_created", "status", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    function: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(default=False, nullable=False)
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("status", "queued")
        kwargs.setdefault("attempts", 0)
        kwargs.setdefault("cancel_requested", False)
        super().__init__(**kwargs)


class ProviderModelValidation(Base):
    __tablename__ = "provider_model_validations"
    __table_args__ = (
        UniqueConstraint("provider_slug", "api_protocol", "model"),
        Index(
            "ix_provider_model_validations_provider_status",
            "provider_slug",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider_slug: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("provider_configurations.slug", ondelete="CASCADE"),
        nullable=False,
    )
    api_protocol: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    tested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_selected: Mapped[bool] = mapped_column(default=False, nullable=False)
    connection_revision: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_auto_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    validation_kind: Mapped[str] = mapped_column(
        String(16), default="probe", nullable=False
    )
    schema_version: Mapped[str | None] = mapped_column(String(64))
    quality_status: Mapped[str | None] = mapped_column(String(32))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    transport_mode: Mapped[str | None] = mapped_column(String(24))
    structured_output_mode: Mapped[str | None] = mapped_column(String(24))


class ApiGroupProvider(Base):
    """A provider slot owned by an ApiGroup (its own API settings set).

    Mirrors ProviderConfiguration's columns; rows are scoped by api_group_id and
    keyed by (api_group_id, slug), so each group can configure its own
    base_url/Key/models independently of the global default set.
    """

    __tablename__ = "api_group_providers"
    __table_args__ = (
        UniqueConstraint("api_group_id", "slug"),
        Index("ix_api_group_providers_group", "api_group_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    api_group_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("api_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    api_protocol: Mapped[str] = mapped_column(
        String(20), default="openai", nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    default_model: Mapped[str] = mapped_column(String(120), nullable=False)
    supported_models: Mapped[list[str]] = mapped_column(
        JSON_TYPE, default=list, nullable=False
    )
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    api_key_last4: Mapped[str | None] = mapped_column(String(4))
    is_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_test_status: Mapped[str] = mapped_column(
        String(16), default="untested", nullable=False
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_message: Mapped[str | None] = mapped_column(String(255))
    validation_revision: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ApiGroupProviderModelValidation(Base):
    """Per-model verification/usage for a group-owned provider slot."""

    __tablename__ = "api_group_provider_model_validations"
    __table_args__ = (
        UniqueConstraint("provider_id", "api_protocol", "model"),
        Index(
            "ix_api_group_provider_models_provider_status",
            "provider_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    api_group_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("api_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("api_group_providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_slug: Mapped[str] = mapped_column(String(32), nullable=False)
    api_protocol: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    tested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_selected: Mapped[bool] = mapped_column(default=False, nullable=False)
    connection_revision: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_auto_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    validation_kind: Mapped[str] = mapped_column(
        String(16), default="probe", nullable=False
    )
    schema_version: Mapped[str | None] = mapped_column(String(64))
    quality_status: Mapped[str | None] = mapped_column(String(32))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    transport_mode: Mapped[str | None] = mapped_column(String(24))
    structured_output_mode: Mapped[str | None] = mapped_column(String(24))


class ApiGroup(Base):
    """A named bundle of API credentials an admin can assign to employees."""

    __tablename__ = "api_groups"
    __table_args__ = (UniqueConstraint("name"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(Text)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    api_key_last4: Mapped[str | None] = mapped_column(String(4))
    default_model: Mapped[str | None] = mapped_column(String(120))
    supported_models: Mapped[list[str]] = mapped_column(
        JSON_TYPE, default=list, nullable=False
    )
    created_by: Mapped[UUID | None] = mapped_column(Uuid)
    updated_by: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username"),
        Index("ix_users_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="employee", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    api_group_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("api_groups.id", ondelete="SET NULL"),
    )
    full_name: Mapped[str | None] = mapped_column(String(80))
    must_change_password: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


__all__ = [
    "AnalysisJob",
    "ApiGroup",
    "Artifact",
    "JobModelAttempt",
    "JobProduct",
    "LocalQueueItem",
    "ProductSnapshot",
    "ProviderConfiguration",
    "ProviderModelValidation",
    "User",
]
