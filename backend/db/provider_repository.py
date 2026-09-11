from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    ApiGroupProvider,
    ApiGroupProviderModelValidation,
    ProviderConfiguration,
    ProviderModelValidation,
)


class ProviderConfigurationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def get(self, slug: str) -> ProviderConfiguration | None:
        statement = select(ProviderConfiguration).where(
            ProviderConfiguration.slug == slug
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[ProviderConfiguration]:
        statement = select(ProviderConfiguration).order_by(
            ProviderConfiguration.created_at,
            ProviderConfiguration.slug,
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def delete_exact_slugs(self, slugs: frozenset[str]) -> int:
        allowed = frozenset({"cattoken", "cattoken_claude"})
        if not slugs or not slugs.issubset(allowed):
            raise ValueError("Only retired CatToken provider slugs may be deleted")
        statement = delete(ProviderConfiguration).where(
            ProviderConfiguration.slug.in_(sorted(slugs))
        )
        result = await self._session.execute(statement)
        await self._session.commit()
        return int(result.rowcount or 0)

    async def list_model_validations(
        self, provider_slug: str
    ) -> list[ProviderModelValidation]:
        statement = (
            select(ProviderModelValidation)
            .where(ProviderModelValidation.provider_slug == provider_slug)
            .order_by(ProviderModelValidation.model)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_model_validation(
        self,
        provider_slug: str,
        api_protocol: str,
        model: str,
    ) -> ProviderModelValidation | None:
        statement = select(ProviderModelValidation).where(
            ProviderModelValidation.provider_slug == provider_slug,
            ProviderModelValidation.api_protocol == api_protocol,
            ProviderModelValidation.model == model,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def upsert_model_validation(
        self,
        *,
        provider_slug: str,
        api_protocol: str,
        model: str,
        status: str,
        error_code: str | None,
        message: str,
        tested_at: datetime,
        connection_revision: int = 1,
        is_automatic: bool = False,
        validation_kind: str = "probe",
        schema_version: str | None = None,
        quality_status: str | None = None,
        duration_ms: int | None = None,
        transport_mode: str | None = None,
        structured_output_mode: str | None = None,
        acted_by: str | None = None,
        acted_at: datetime | None = None,
    ) -> ProviderModelValidation:
        statement = select(ProviderModelValidation).where(
            ProviderModelValidation.provider_slug == provider_slug,
            ProviderModelValidation.api_protocol == api_protocol,
            ProviderModelValidation.model == model,
        )
        result = await self._session.execute(statement)
        record = result.scalar_one_or_none()
        values = {
            "status": status,
            "error_code": error_code,
            "message": message,
            "tested_at": tested_at,
            "connection_revision": connection_revision,
            "validation_kind": validation_kind,
            "schema_version": schema_version,
            "quality_status": quality_status,
            "duration_ms": duration_ms,
            "transport_mode": transport_mode,
            "structured_output_mode": structured_output_mode,
        }
        if is_automatic:
            values["last_auto_tested_at"] = tested_at
        if acted_by is not None:
            values["last_acted_by"] = acted_by
        if acted_at is not None:
            values["last_acted_at"] = acted_at
        if record is None:
            record = ProviderModelValidation(
                provider_slug=provider_slug,
                api_protocol=api_protocol,
                model=model,
                **values,
            )
            self._session.add(record)
        else:
            for name, value in values.items():
                setattr(record, name, value)
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def record_full_report_validation(
        self,
        *,
        provider_slug: str,
        api_protocol: str,
        model: str,
        status: str,
        error_code: str | None,
        message: str,
        tested_at: datetime,
        connection_revision: int,
        schema_version: str,
        quality_status: str,
        duration_ms: int | None = None,
    ) -> ProviderModelValidation:
        existing = await self.get_model_validation(
            provider_slug,
            api_protocol,
            model,
        )
        return await self.upsert_model_validation(
            provider_slug=provider_slug,
            api_protocol=api_protocol,
            model=model,
            status=status,
            error_code=error_code,
            message=message,
            tested_at=tested_at,
            connection_revision=connection_revision,
            validation_kind="full_report",
            schema_version=schema_version,
            quality_status=quality_status,
            duration_ms=duration_ms,
            transport_mode=getattr(existing, "transport_mode", None),
            structured_output_mode=getattr(
                existing, "structured_output_mode", None
            ),
        )

    async def is_full_report_verified(
        self,
        provider_slug: str,
        api_protocol: str,
        model: str,
        connection_revision: int,
        *,
        schema_version: str | None = None,
    ) -> bool:
        record = await self.get_model_validation(provider_slug, api_protocol, model)
        if record is None:
            return False
        return (
            getattr(record, "validation_kind", "probe") == "full_report"
            and record.status == "verified"
            and getattr(record, "quality_status", None) == "passed"
            and int(getattr(record, "connection_revision", 1)) == int(connection_revision)
            and (schema_version is None or getattr(record, "schema_version", None) == schema_version)
        )

    async def record_model_usage(
        self,
        provider_slug: str,
        api_protocol: str,
        model: str,
        used_at: datetime,
    ) -> ProviderModelValidation | None:
        statement = select(ProviderModelValidation).where(
            ProviderModelValidation.provider_slug == provider_slug,
            ProviderModelValidation.api_protocol == api_protocol,
            ProviderModelValidation.model == model,
        )
        result = await self._session.execute(statement)
        record = result.scalar_one_or_none()
        if record is None:
            return None
        record.last_used_at = used_at
        record.use_count = int(record.use_count or 0) + 1
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def increment_validation_revision(
        self, provider_slug: str
    ) -> ProviderConfiguration | None:
        record = await self.get(provider_slug)
        if record is None:
            return None
        record.validation_revision = int(record.validation_revision or 1) + 1
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def delete_model_validations(self, provider_slug: str) -> int:
        statement = delete(ProviderModelValidation).where(
            ProviderModelValidation.provider_slug == provider_slug
        )
        result = await self._session.execute(statement)
        await self._session.commit()
        return int(result.rowcount or 0)

    async def set_model_selected(
        self,
        provider_slug: str,
        api_protocol: str,
        model: str,
        is_selected: bool,
        acted_by: str | None = None,
        acted_at: datetime | None = None,
    ) -> ProviderModelValidation | None:
        statement = select(ProviderModelValidation).where(
            ProviderModelValidation.provider_slug == provider_slug,
            ProviderModelValidation.api_protocol == api_protocol,
            ProviderModelValidation.model == model,
        )
        result = await self._session.execute(statement)
        record = result.scalar_one_or_none()
        if record is None:
            return None
        record.is_selected = is_selected
        if acted_by is not None:
            record.last_acted_by = acted_by
        if acted_at is not None:
            record.last_acted_at = acted_at
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def set_default_model(
        self, provider_slug: str, model: str
    ) -> ProviderConfiguration | None:
        record = await self.get(provider_slug)
        if record is None:
            return None
        record.default_model = model
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def upsert(
        self,
        *,
        slug: str,
        provider_type: str,
        display_name: str,
        base_url: str | None,
        default_model: str,
        supported_models: list[str],
        encrypted_api_key: str | None,
        api_key_last4: str | None,
        is_enabled: bool,
        last_test_status: str,
        last_test_message: str | None,
        api_protocol: str = "openai",
        last_tested_at: datetime | None = None,
    ) -> ProviderConfiguration:
        record = await self.get(slug)
        values = {
            "provider_type": provider_type,
            "api_protocol": api_protocol,
            "display_name": display_name,
            "base_url": base_url,
            "default_model": default_model,
            "supported_models": supported_models,
            "encrypted_api_key": encrypted_api_key,
            "api_key_last4": api_key_last4,
            "is_enabled": is_enabled,
            "last_test_status": last_test_status,
            "last_test_message": last_test_message,
            "last_tested_at": last_tested_at,
        }
        if record is None:
            record = ProviderConfiguration(slug=slug, **values)
            self._session.add(record)
        else:
            for name, value in values.items():
                setattr(record, name, value)

        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def record_test_failure(
        self,
        *,
        slug: str,
        message: str,
        tested_at: datetime,
    ) -> ProviderConfiguration | None:
        record = await self.get(slug)
        if record is None:
            return None
        record.supported_models = []
        record.last_test_status = "failed"
        record.last_test_message = message
        record.last_tested_at = tested_at
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def record_test_success(
        self,
        *,
        slug: str,
        models: list[str],
        message: str,
        tested_at: datetime,
    ) -> ProviderConfiguration | None:
        record = await self.get(slug)
        if record is None:
            return None
        record.supported_models = models
        record.last_test_status = "success"
        record.last_test_message = message
        record.last_tested_at = tested_at
        await self._session.commit()
        await self._session.refresh(record)
        return record


class GroupProviderRepository:
    """ProviderConfigurationRepository equivalent scoped to ONE ApiGroup.

    Backs an ApiGroup's own multi-provider API settings (its rows live in
    api_group_providers / api_group_provider_model_validations and are filtered
    by this repository's api_group_id). Method surface mirrors the global
    repository so ProviderService/ProviderClientResolver can run unchanged over
    either scope.
    """

    def __init__(self, session: AsyncSession, *, api_group_id: UUID) -> None:
        self._session = session
        self._api_group_id = api_group_id

    @property
    def api_group_id(self) -> UUID:
        return self._api_group_id

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def _resolve_provider(self, slug: str) -> ApiGroupProvider | None:
        statement = select(ApiGroupProvider).where(
            ApiGroupProvider.api_group_id == self._api_group_id,
            ApiGroupProvider.slug == slug,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get(self, slug: str) -> ApiGroupProvider | None:
        return await self._resolve_provider(slug)

    async def list_all(self) -> list[ApiGroupProvider]:
        statement = (
            select(ApiGroupProvider)
            .where(ApiGroupProvider.api_group_id == self._api_group_id)
            .order_by(ApiGroupProvider.created_at, ApiGroupProvider.slug)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_model_validations(
        self, provider_slug: str
    ) -> list[ApiGroupProviderModelValidation]:
        statement = (
            select(ApiGroupProviderModelValidation)
            .where(
                ApiGroupProviderModelValidation.api_group_id == self._api_group_id,
                ApiGroupProviderModelValidation.provider_slug == provider_slug,
            )
            .order_by(ApiGroupProviderModelValidation.model)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_model_validation(
        self, provider_slug: str, api_protocol: str, model: str
    ) -> ApiGroupProviderModelValidation | None:
        statement = select(ApiGroupProviderModelValidation).where(
            ApiGroupProviderModelValidation.api_group_id == self._api_group_id,
            ApiGroupProviderModelValidation.provider_slug == provider_slug,
            ApiGroupProviderModelValidation.api_protocol == api_protocol,
            ApiGroupProviderModelValidation.model == model,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def upsert_model_validation(
        self,
        *,
        provider_slug: str,
        api_protocol: str,
        model: str,
        status: str,
        error_code: str | None,
        message: str,
        tested_at: datetime,
        connection_revision: int = 1,
        is_automatic: bool = False,
        validation_kind: str = "probe",
        schema_version: str | None = None,
        quality_status: str | None = None,
        duration_ms: int | None = None,
        transport_mode: str | None = None,
        structured_output_mode: str | None = None,
        acted_by: str | None = None,
        acted_at: datetime | None = None,
    ) -> ApiGroupProviderModelValidation:
        provider = await self._resolve_provider(provider_slug)
        if provider is None:
            raise ValueError(f"Group provider slot not configured: {provider_slug}")
        statement = select(ApiGroupProviderModelValidation).where(
            ApiGroupProviderModelValidation.api_group_id == self._api_group_id,
            ApiGroupProviderModelValidation.provider_slug == provider_slug,
            ApiGroupProviderModelValidation.api_protocol == api_protocol,
            ApiGroupProviderModelValidation.model == model,
        )
        result = await self._session.execute(statement)
        record = result.scalar_one_or_none()
        values = {
            "status": status,
            "error_code": error_code,
            "message": message,
            "tested_at": tested_at,
            "connection_revision": connection_revision,
            "validation_kind": validation_kind,
            "schema_version": schema_version,
            "quality_status": quality_status,
            "duration_ms": duration_ms,
            "transport_mode": transport_mode,
            "structured_output_mode": structured_output_mode,
        }
        if is_automatic:
            values["last_auto_tested_at"] = tested_at
        if acted_by is not None:
            values["last_acted_by"] = acted_by
        if acted_at is not None:
            values["last_acted_at"] = acted_at
        if record is None:
            record = ApiGroupProviderModelValidation(
                api_group_id=self._api_group_id,
                provider_id=provider.id,
                provider_slug=provider_slug,
                api_protocol=api_protocol,
                model=model,
                **values,
            )
            self._session.add(record)
        else:
            for name, value in values.items():
                setattr(record, name, value)
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def record_full_report_validation(
        self,
        *,
        provider_slug: str,
        api_protocol: str,
        model: str,
        status: str,
        error_code: str | None,
        message: str,
        tested_at: datetime,
        connection_revision: int,
        schema_version: str,
        quality_status: str,
        duration_ms: int | None = None,
    ) -> ApiGroupProviderModelValidation:
        existing = await self.get_model_validation(
            provider_slug, api_protocol, model
        )
        return await self.upsert_model_validation(
            provider_slug=provider_slug,
            api_protocol=api_protocol,
            model=model,
            status=status,
            error_code=error_code,
            message=message,
            tested_at=tested_at,
            connection_revision=connection_revision,
            validation_kind="full_report",
            schema_version=schema_version,
            quality_status=quality_status,
            duration_ms=duration_ms,
            transport_mode=getattr(existing, "transport_mode", None),
            structured_output_mode=getattr(
                existing, "structured_output_mode", None
            ),
        )

    async def is_full_report_verified(
        self,
        provider_slug: str,
        api_protocol: str,
        model: str,
        connection_revision: int,
        *,
        schema_version: str | None = None,
    ) -> bool:
        record = await self.get_model_validation(provider_slug, api_protocol, model)
        if record is None:
            return False
        return (
            getattr(record, "validation_kind", "probe") == "full_report"
            and record.status == "verified"
            and getattr(record, "quality_status", None) == "passed"
            and int(getattr(record, "connection_revision", 1)) == int(connection_revision)
            and (schema_version is None or getattr(record, "schema_version", None) == schema_version)
        )

    async def record_model_usage(
        self, provider_slug: str, api_protocol: str, model: str, used_at: datetime
    ) -> ApiGroupProviderModelValidation | None:
        record = await self.get_model_validation(provider_slug, api_protocol, model)
        if record is None:
            return None
        record.last_used_at = used_at
        record.use_count = int(record.use_count or 0) + 1
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def increment_validation_revision(
        self, provider_slug: str
    ) -> ApiGroupProvider | None:
        record = await self._resolve_provider(provider_slug)
        if record is None:
            return None
        record.validation_revision = int(record.validation_revision or 1) + 1
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def delete_model_validations(self, provider_slug: str) -> int:
        statement = delete(ApiGroupProviderModelValidation).where(
            ApiGroupProviderModelValidation.api_group_id == self._api_group_id,
            ApiGroupProviderModelValidation.provider_slug == provider_slug,
        )
        result = await self._session.execute(statement)
        await self._session.commit()
        return int(result.rowcount or 0)

    async def set_model_selected(
        self,
        provider_slug: str,
        api_protocol: str,
        model: str,
        is_selected: bool,
        acted_by: str | None = None,
        acted_at: datetime | None = None,
    ) -> ApiGroupProviderModelValidation | None:
        record = await self.get_model_validation(provider_slug, api_protocol, model)
        if record is None:
            return None
        record.is_selected = is_selected
        if acted_by is not None:
            record.last_acted_by = acted_by
        if acted_at is not None:
            record.last_acted_at = acted_at
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def set_default_model(
        self, provider_slug: str, model: str
    ) -> ApiGroupProvider | None:
        record = await self._resolve_provider(provider_slug)
        if record is None:
            return None
        record.default_model = model
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def upsert(
        self,
        *,
        slug: str,
        provider_type: str,
        display_name: str,
        base_url: str | None,
        default_model: str,
        supported_models: list[str],
        encrypted_api_key: str | None,
        api_key_last4: str | None,
        is_enabled: bool,
        last_test_status: str,
        last_test_message: str | None,
        api_protocol: str = "openai",
        last_tested_at: datetime | None = None,
    ) -> ApiGroupProvider:
        record = await self._resolve_provider(slug)
        values = {
            "provider_type": provider_type,
            "api_protocol": api_protocol,
            "display_name": display_name,
            "base_url": base_url,
            "default_model": default_model,
            "supported_models": supported_models,
            "encrypted_api_key": encrypted_api_key,
            "api_key_last4": api_key_last4,
            "is_enabled": is_enabled,
            "last_test_status": last_test_status,
            "last_test_message": last_test_message,
            "last_tested_at": last_tested_at,
        }
        if record is None:
            record = ApiGroupProvider(
                api_group_id=self._api_group_id,
                slug=slug,
                **values,
            )
            self._session.add(record)
        else:
            for name, value in values.items():
                setattr(record, name, value)
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def record_test_failure(
        self, *, slug: str, message: str, tested_at: datetime
    ) -> ApiGroupProvider | None:
        record = await self._resolve_provider(slug)
        if record is None:
            return None
        record.supported_models = []
        record.last_test_status = "failed"
        record.last_test_message = message
        record.last_tested_at = tested_at
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def record_test_success(
        self, *, slug: str, models: list[str], message: str, tested_at: datetime
    ) -> ApiGroupProvider | None:
        record = await self._resolve_provider(slug)
        if record is None:
            return None
        record.supported_models = models
        record.last_test_status = "success"
        record.last_test_message = message
        record.last_tested_at = tested_at
        await self._session.commit()
        await self._session.refresh(record)
        return record


__all__ = ["GroupProviderRepository", "ProviderConfigurationRepository"]
