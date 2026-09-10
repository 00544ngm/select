from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from hmac import compare_digest

from app.infrastructure.llm.anthropic_client import normalize_anthropic_base_url
from app.infrastructure.llm.openai_compat import normalize_openai_compatible_base_url
from backend.api.schemas.providers import (
    ProviderApiProtocol,
    ProviderDraft,
    ProviderModelOption,
    ProviderModelSelectionResult,
    ProviderModelVerifyResult,
    ProviderPublic,
    ProviderUpdate,
)
from backend.application.provider_clients import (
    ProviderConnectionError,
    ProviderConnectionTestResult,
    ProviderModelVerifier,
    ProviderRuntimeConfig,
)
from backend.db.provider_repository import ProviderConfigurationRepository
from backend.security.provider_crypto import ProviderCrypto, ProviderDecryptionError


@dataclass(frozen=True)
class ProviderSlot:
    provider_type: str
    api_protocol: ProviderApiProtocol
    display_name: str
    role: str
    base_url: str | None
    default_model: str


PROVIDER_SLOTS: dict[str, ProviderSlot] = {
    "openai": ProviderSlot(
        "openai", "openai", "OpenAI", "primary", "https://api.openai.com/v1", "gpt-4o"
    ),
    "deepseek": ProviderSlot(
        "openai_compatible",
        "openai",
        "DeepSeek",
        "secondary",
        "https://api.deepseek.com",
        "deepseek-chat",
    ),
    "custom": ProviderSlot(
        "openai_compatible", "openai", "自定义 API", "primary", None, "gpt-4o"
    ),
    "claude": ProviderSlot(
        "anthropic",
        "anthropic",
        "Claude",
        "primary",
        "https://maike-ai.top",
        "claude-opus-5",
    ),
}


class ProviderConfigurationError(RuntimeError):
    def __init__(self, *, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


ConnectionTest = Callable[[ProviderRuntimeConfig], Awaitable[ProviderConnectionTestResult]]
ModelVerifier = Callable[..., Awaitable]


class ProviderService:
    def __init__(
        self,
        *,
        repository: ProviderConfigurationRepository,
        crypto: ProviderCrypto,
        connection_test: ConnectionTest,
        model_verifier: ModelVerifier | None = None,
    ) -> None:
        self._repository = repository
        self._crypto = crypto
        self._connection_test = connection_test
        self._model_verifier = model_verifier or ProviderModelVerifier()

    async def list_public(self) -> list[ProviderPublic]:
        records = {record.slug: record for record in await self._repository.list_all()}
        providers = []
        for slug in PROVIDER_SLOTS:
            validations = await self._repository.list_model_validations(slug)
            providers.append(self._to_public(slug, records.get(slug), validations))
        return providers

    async def is_available(self, slug: str) -> bool:
        slot = PROVIDER_SLOTS.get(slug)
        if slot is None or slot.role != "primary":
            return False
        record = await self._repository.get(slug)
        if record is not None:
            return bool(record.is_enabled and record.encrypted_api_key)

        from app.core.config import settings as legacy_settings

        return bool(getattr(legacy_settings, f"{slug}_api_key", ""))

    async def is_model_available(self, slug: str, model: str | None) -> bool:
        slot = PROVIDER_SLOTS.get(slug)
        if slot is None or slot.role != "primary":
            return False
        record = await self._repository.get(slug)
        if record is None or not record.is_enabled or not record.encrypted_api_key:
            return False
        selected_model = model or record.default_model
        validations = await self._repository.list_model_validations(slug)
        for validation in validations:
            if (
                validation.api_protocol == record.api_protocol
                and validation.model == selected_model
                and validation.status == "verified"
                and bool(getattr(validation, "is_selected", False))
                and int(getattr(validation, "connection_revision", 1))
                == int(getattr(record, "validation_revision", 1))
            ):
                return True
        return False

    async def import_legacy_env(self, legacy_settings) -> None:
        for slug in ("openai", "deepseek"):
            api_key = getattr(legacy_settings, f"{slug}_api_key", "")
            if not api_key:
                continue
            if await self._repository.get(slug) is not None:
                continue

            slot = PROVIDER_SLOTS[slug]
            model = getattr(
                legacy_settings,
                f"{slug}_model",
                slot.default_model,
            )
            base_url = getattr(
                legacy_settings,
                f"{slug}_base_url",
                slot.base_url,
            )
            await self._repository.upsert(
                slug=slug,
                provider_type=slot.provider_type,
                api_protocol=slot.api_protocol,
                display_name=slot.display_name,
                base_url=base_url,
                default_model=model,
                supported_models=[],
                encrypted_api_key=self._crypto.encrypt(api_key),
                api_key_last4=(api_key[-4:] if len(api_key) >= 4 else None),
                is_enabled=True,
                last_test_status="untested",
                last_test_message="Imported from environment",
                last_tested_at=None,
            )

    async def test_draft(
        self, slug: str, draft: ProviderDraft
    ) -> ProviderConnectionTestResult:
        existing = await self._repository.get(slug)
        runtime, _key, _cipher, _last4 = self._resolve_runtime(slug, draft, existing)
        try:
            result = await self._connection_test(runtime)
            if existing is not None:
                await self._repository.record_test_success(
                    slug=slug,
                    models=list(result.models),
                    message=result.message,
                    tested_at=datetime.now(timezone.utc),
                )
            return result
        except ProviderConnectionError as error:
            if existing is not None:
                await self._repository.record_test_failure(
                    slug=slug,
                    message=error.message,
                    tested_at=datetime.now(timezone.utc),
                )
            raise

    async def save(self, slug: str, update: ProviderUpdate) -> ProviderPublic:
        existing = await self._repository.get(slug)
        runtime, key, cipher, last4 = self._resolve_runtime(slug, update, existing)
        key_changed = False
        if update.api_key is not None:
            supplied_key = update.api_key.get_secret_value()
            encrypted_existing_key = getattr(existing, "encrypted_api_key", None)
            if encrypted_existing_key:
                try:
                    existing_key = self._crypto.decrypt(encrypted_existing_key)
                except ProviderDecryptionError:
                    key_changed = True
                else:
                    key_changed = not compare_digest(existing_key, supplied_key)
            else:
                key_changed = True
        invalidates_models = existing is not None and (
            runtime.api_protocol != getattr(existing, "api_protocol", "openai")
            or runtime.base_url != getattr(existing, "base_url", None)
            or key_changed
            or update.clear_api_key
        )

        if update.clear_api_key:
            key = None
            cipher = None
            last4 = None

        if update.is_enabled and not key:
            raise ProviderConfigurationError(
                code="PROVIDER_NOT_CONFIGURED",
                message="An API key is required before enabling this provider",
            )

        tested_at = getattr(existing, "last_tested_at", None)
        test_status = getattr(existing, "last_test_status", "untested")
        test_message = getattr(existing, "last_test_message", None)
        supported_models = list(getattr(existing, "supported_models", []) or [])
        if existing is None or invalidates_models:
            tested_at = None
            test_status = "untested"
            test_message = None
            supported_models = []

        slot = PROVIDER_SLOTS[slug]
        if invalidates_models:
            revised = await self._repository.increment_validation_revision(slug)
            if revised is not None:
                existing = revised

        record = await self._repository.upsert(
            slug=slug,
            provider_type=slot.provider_type,
            api_protocol=runtime.api_protocol,
            display_name=runtime.display_name,
            base_url=runtime.base_url,
            default_model=runtime.default_model,
            supported_models=supported_models,
            encrypted_api_key=cipher,
            api_key_last4=last4,
            is_enabled=update.is_enabled,
            last_test_status=test_status,
            last_test_message=test_message,
            last_tested_at=tested_at,
        )
        validations = await self._repository.list_model_validations(slug)
        return self._to_public(slug, record, validations)

    async def verify_model(
        self,
        slug: str,
        model: str,
        *,
        set_default: bool = True,
        is_automatic: bool = False,
    ) -> ProviderModelVerifyResult:
        record = await self._repository.get(slug)
        if record is None or not record.encrypted_api_key:
            raise ProviderConfigurationError(
                code="PROVIDER_NOT_CONFIGURED",
                message="请先保存供应商配置和 API Key",
            )
        if not record.is_enabled:
            raise ProviderConfigurationError(
                code="PROVIDER_DISABLED",
                message="请先启用该供应商",
            )
        try:
            api_key = self._crypto.decrypt(record.encrypted_api_key)
        except ProviderDecryptionError as error:
            raise ProviderConfigurationError(
                code="PROVIDER_CONFIG_DECRYPT_FAILED",
                message="API Key 必须重新录入",
            ) from error
        runtime = ProviderRuntimeConfig(
            slug=slug,
            provider_type=record.provider_type,
            api_protocol=record.api_protocol,
            display_name=record.display_name,
            role=PROVIDER_SLOTS[slug].role,
            base_url=record.base_url,
            default_model=record.default_model,
            api_key=api_key,
            supported_models=tuple(record.supported_models or []),
        )
        probe = await self._model_verifier(runtime, model)
        tested_at = datetime.now(timezone.utc)
        await self._repository.upsert_model_validation(
            provider_slug=slug,
            api_protocol=record.api_protocol,
            model=model,
            status=probe.status,
            error_code=probe.error_code,
            message=probe.message,
            tested_at=tested_at,
            connection_revision=int(getattr(record, "validation_revision", 1)),
            is_automatic=is_automatic,
            transport_mode=getattr(probe, "transport_mode", None),
            structured_output_mode=getattr(
                probe, "structured_output_mode", None
            ),
        )
        is_default = model == record.default_model
        if probe.status == "verified" and set_default:
            await self._repository.set_default_model(slug, model)
            is_default = True
        return ProviderModelVerifyResult(
            provider=slug,
            model=model,
            test_status=probe.status,
            tested_at=tested_at,
            test_message=probe.message,
            error_code=probe.error_code,
            is_default=is_default,
            transport_mode=getattr(probe, "transport_mode", None),
            structured_output_mode=getattr(
                probe, "structured_output_mode", None
            ),
        )

    async def set_model_selected(
        self, slug: str, model: str, is_selected: bool
    ) -> ProviderModelSelectionResult:
        record = await self._repository.get(slug)
        if record is None or not record.is_enabled:
            raise ProviderConfigurationError(
                code="PROVIDER_NOT_CONFIGURED",
                message="请先保存并启用供应商配置",
            )
        validation = next(
            (
                item
                for item in await self._repository.list_model_validations(slug)
                if item.api_protocol == record.api_protocol and item.model == model
            ),
            None,
        )
        if is_selected and (
            validation is None
            or validation.status != "verified"
            or int(getattr(validation, "connection_revision", 1))
            != int(getattr(record, "validation_revision", 1))
        ):
            raise ProviderConfigurationError(
                code="PROVIDER_MODEL_NOT_VERIFIED",
                message="只有当前连接验证成功的模型才能勾选使用",
            )
        updated = await self._repository.set_model_selected(
            slug, record.api_protocol, model, is_selected
        )
        if updated is None:
            raise ProviderConfigurationError(
                code="PROVIDER_MODEL_NOT_FOUND",
                message="未找到该模型的验证记录",
            )
        return ProviderModelSelectionResult(
            provider=slug,
            model=model,
            is_selected=is_selected,
        )

    async def record_model_usage(self, slug: str, model: str | None) -> None:
        record = await self._repository.get(slug)
        if record is None:
            return
        selected_model = model or record.default_model
        await self._repository.record_model_usage(
            slug,
            record.api_protocol,
            selected_model,
            datetime.now(timezone.utc),
        )

    def _resolve_runtime(self, slug: str, draft: ProviderDraft, existing):
        slot = PROVIDER_SLOTS.get(slug)
        if slot is None:
            raise ProviderConfigurationError(
                code="PROVIDER_NOT_FOUND",
                message="Unknown provider configuration",
            )

        display_name = (
            draft.display_name
            or getattr(existing, "display_name", None)
            or slot.display_name
            if slug == "custom"
            else slot.display_name
        )
        base_url = str(draft.base_url).rstrip("/") if draft.base_url else (
            getattr(existing, "base_url", None) or slot.base_url
        )
        if slug == "custom" and not base_url:
            raise ProviderConfigurationError(
                code="PROVIDER_ENDPOINT_INVALID",
                message="A base URL is required for the custom provider",
            )
        api_protocol = draft.api_protocol
        if slug != "custom" and api_protocol != slot.api_protocol:
            raise ProviderConfigurationError(
                code="PROVIDER_PROTOCOL_INVALID",
                message="The selected protocol does not match this provider",
            )
        if slug == "custom" and base_url:
            if api_protocol == "anthropic":
                try:
                    base_url = normalize_anthropic_base_url(base_url)
                except ValueError as error:
                    raise ProviderConfigurationError(
                        code="PROVIDER_ENDPOINT_INVALID",
                        message=str(error),
                    ) from error
            elif api_protocol == "openai":
                try:
                    base_url = normalize_openai_compatible_base_url(base_url)
                except ValueError as error:
                    raise ProviderConfigurationError(
                        code="PROVIDER_ENDPOINT_INVALID",
                        message=str(error),
                    ) from error

        supplied_key = draft.api_key.get_secret_value() if draft.api_key else None
        cipher = getattr(existing, "encrypted_api_key", None)
        last4 = getattr(existing, "api_key_last4", None)
        key = supplied_key
        if supplied_key:
            cipher = self._crypto.encrypt(supplied_key)
            last4 = supplied_key[-4:] if len(supplied_key) >= 4 else None
        elif cipher:
            try:
                key = self._crypto.decrypt(cipher)
            except ProviderDecryptionError as error:
                raise ProviderConfigurationError(
                    code="PROVIDER_CONFIG_DECRYPT_FAILED",
                    message="The API key must be re-entered",
                ) from error

        if not key:
            raise ProviderConfigurationError(
                code="PROVIDER_NOT_CONFIGURED",
                message="An API key is required",
            )

        runtime = ProviderRuntimeConfig(
            slug=slug,
            provider_type=slot.provider_type,
            api_protocol=api_protocol,
            display_name=display_name,
            role=slot.role,
            base_url=base_url,
            default_model=draft.default_model,
            api_key=key,
        )
        return runtime, key, cipher, last4

    @staticmethod
    def _to_public(slug: str, record, validations=()) -> ProviderPublic:
        slot = PROVIDER_SLOTS[slug]
        if record is None:
            return ProviderPublic(
                slug=slug,
                api_protocol=slot.api_protocol,
                display_name=slot.display_name,
                role=slot.role,
                base_url=slot.base_url,
                default_model=slot.default_model,
                supported_models=[],
                model_options=[],
                is_enabled=False,
                configured=False,
                masked_api_key=None,
                last_test_status="untested",
                last_tested_at=None,
                last_test_message=None,
                updated_at=None,
            )
        validation_by_model = {
            validation.model: validation
            for validation in validations
            if validation.api_protocol == record.api_protocol
        }
        models = list(record.supported_models or [])
        for model in validation_by_model:
            if model not in models:
                models.append(model)
        public = ProviderPublic(
            slug=slug,
            api_protocol=(
                record.api_protocol if slug == "custom" else slot.api_protocol
            ),
            display_name=(
                record.display_name if slug == "custom" else slot.display_name
            ),
            role=slot.role,
            base_url=record.base_url,
            default_model=record.default_model,
            supported_models=models,
            is_enabled=record.is_enabled,
            configured=bool(record.encrypted_api_key),
            masked_api_key=(
                f"••••{record.api_key_last4}" if record.api_key_last4 else "••••"
            ) if record.encrypted_api_key else None,
            last_test_status=record.last_test_status,
            last_tested_at=record.last_tested_at,
            last_test_message=record.last_test_message,
            updated_at=getattr(record, "updated_at", None),
        )
        public.model_options = []
        for model in models:
            validation = validation_by_model.get(model)
            is_current_connection = (
                validation is None
                or int(getattr(validation, "connection_revision", 1))
                == int(getattr(record, "validation_revision", 1))
            )
            public.model_options.append(
                ProviderModelOption(
                provider=slug,
                provider_display_name=public.display_name,
                api_protocol=public.api_protocol,
                model=model,
                is_default=model == public.default_model,
                is_selected=bool(getattr(validation, "is_selected", False)),
                is_enabled=public.is_enabled,
                    test_status=(validation.status if validation else "discovered"),
                    tested_at=(validation.tested_at if validation else None),
                    test_message=(
                        validation.message
                        if validation
                        else "目录发现，尚未真实验证"
                    ),
                    error_code=(validation.error_code if validation else None),
                    connection_revision=int(
                        getattr(validation, "connection_revision", 1)
                    ),
                    current_connection_revision=int(
                        getattr(record, "validation_revision", 1)
                    ),
                    is_current_connection=is_current_connection,
                    last_used_at=(
                        getattr(validation, "last_used_at", None)
                        if validation
                        else None
                    ),
                    use_count=(
                        int(getattr(validation, "use_count", 0) or 0)
                        if validation
                        else 0
                    ),
                    last_auto_tested_at=(
                        getattr(validation, "last_auto_tested_at", None)
                        if validation
                        else None
                    ),
                    transport_mode=(
                        getattr(validation, "transport_mode", None)
                        if validation and is_current_connection
                        else None
                    ),
                    structured_output_mode=(
                        getattr(validation, "structured_output_mode", None)
                        if validation and is_current_connection
                        else None
                    ),
                )
            )
        return public


__all__ = [
    "PROVIDER_SLOTS",
    "ProviderConfigurationError",
    "ProviderService",
]
