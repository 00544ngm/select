from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import SecretStr

from backend.api.schemas.providers import ProviderDraft, ProviderUpdate
from backend.application.provider_clients import (
    ProviderConnectionError,
    ProviderConnectionTestResult,
    ProviderModelVerificationResult,
)
from backend.application.provider_service import (
    ProviderConfigurationError,
    ProviderService,
)
from backend.security.provider_crypto import ProviderCrypto, ProviderDecryptionError


def provider_row(**overrides):
    values = {
        "slug": "openai",
        "provider_type": "openai",
        "api_protocol": "openai",
        "display_name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "supported_models": [],
        "encrypted_api_key": None,
        "api_key_last4": None,
        "is_enabled": False,
        "last_test_status": "untested",
        "last_tested_at": None,
        "last_test_message": None,
        "validation_revision": 1,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_model_availability_does_not_decrypt_key_or_probe_current_validation():
    repository = AsyncMock()
    repository.get.return_value = provider_row(
        encrypted_api_key="dpapi:other-user",
        is_enabled=True,
    )
    repository.list_model_validations.return_value = [
        SimpleNamespace(
            api_protocol="openai",
            model="gpt-4o",
            status="verified",
            tested_at=datetime.now(timezone.utc),
            is_selected=True,
        )
    ]
    crypto = Mock()
    crypto.decrypt.side_effect = ProviderDecryptionError("re-entered")
    verifier = AsyncMock()
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
        model_verifier=verifier,
    )

    assert await service.is_model_available("openai", "gpt-4o") is True
    crypto.decrypt.assert_not_called()
    verifier.assert_not_awaited()


@pytest.mark.asyncio
async def test_model_is_available_with_old_verification_for_current_connection(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = provider_row(
        default_model="model-a",
        encrypted_api_key=crypto.encrypt("sk-test"),
        is_enabled=True,
    )
    repository.list_model_validations.return_value = [
        SimpleNamespace(
            api_protocol="openai",
            model="model-a",
            status="verified",
            tested_at=datetime.now(timezone.utc) - timedelta(days=30),
            is_selected=True,
            connection_revision=1,
        )
    ]
    verifier = AsyncMock(
        return_value=ProviderModelVerificationResult(
            model="model-a",
            status="verified",
            message="结构化验证成功",
        )
    )
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
        model_verifier=verifier,
    )

    assert await service.is_model_available("openai", None) is True
    verifier.assert_not_awaited()
    repository.upsert_model_validation.assert_not_awaited()

    repository.list_model_validations.return_value[0].connection_revision = 0
    assert await service.is_model_available("openai", "model-a") is False
    verifier.assert_not_awaited()


@pytest.mark.asyncio
async def test_availability_uses_persisted_status_without_live_probe(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = provider_row(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="openai",
        display_name="Maike",
        base_url="https://maike-ai.top/v1",
        default_model="claude-opus-4-5-20251101",
        encrypted_api_key=crypto.encrypt("sk-test"),
        is_enabled=True,
    )
    repository.list_model_validations.return_value = [
        SimpleNamespace(
            api_protocol="openai",
            model="claude-opus-4-5-20251101",
            status="verified",
            tested_at=datetime.now(timezone.utc),
            is_selected=True,
        )
    ]
    verifier = AsyncMock(
        return_value=ProviderModelVerificationResult(
            model="claude-opus-4-5-20251101",
            status="unavailable",
            message="当前模型不存在或暂不可用",
            error_code="PROVIDER_MODEL_INVALID",
        )
    )
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
        model_verifier=verifier,
    )

    assert await service.is_model_available("custom", "claude-opus-4-5-20251101") is True
    verifier.assert_not_awaited()
    repository.upsert_model_validation.assert_not_awaited()
    repository.set_model_selected.assert_not_awaited()


@pytest.mark.asyncio
async def test_availability_rejects_persisted_temporary_error_without_live_probe(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = provider_row(
        encrypted_api_key=crypto.encrypt("sk-test"),
        is_enabled=True,
    )
    repository.list_model_validations.return_value = [
        SimpleNamespace(
            api_protocol="openai",
            model="gpt-4o",
            status="temporary_error",
            tested_at=datetime.now(timezone.utc),
            is_selected=True,
        )
    ]
    verifier = AsyncMock(
        return_value=ProviderModelVerificationResult(
            model="gpt-4o",
            status="temporary_error",
            message="供应商暂时限流，请稍后重试",
            error_code="PROVIDER_RATE_LIMITED",
        )
    )
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
        model_verifier=verifier,
    )

    assert await service.is_model_available("openai", "gpt-4o") is False
    verifier.assert_not_awaited()
    repository.upsert_model_validation.assert_not_awaited()
    repository.set_model_selected.assert_not_awaited()
    assert await service.is_model_available("openai", "model-a") is False


@pytest.mark.asyncio
async def test_list_public_omits_retired_cattoken_slots_and_masks_saved_key(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.list_all.return_value = [
        provider_row(
            encrypted_api_key=crypto.encrypt("sk-secret-4F2A"),
            api_key_last4="4F2A",
            is_enabled=True,
            last_test_status="success",
        )
    ]
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
    )

    result = await service.list_public()

    assert [item.slug for item in result] == [
        "openai",
        "deepseek",
        "custom",
        "claude",
    ]
    assert result[0].configured is True
    assert result[0].masked_api_key == "••••4F2A"
    assert result[0].api_protocol == "openai"
    assert result[2].api_protocol == "openai"
    assert result[1].role == "secondary"


@pytest.mark.asyncio
async def test_list_public_ignores_saved_retired_cattoken_records(tmp_path):
    repository = AsyncMock()
    repository.list_all.return_value = [
        provider_row(slug="cattoken", is_enabled=True),
        provider_row(slug="cattoken_claude", is_enabled=True),
    ]
    service = ProviderService(
        repository=repository,
        crypto=ProviderCrypto(key_file=tmp_path / "provider.key"),
        connection_test=AsyncMock(),
    )

    result = await service.list_public()

    assert [item.slug for item in result] == ["openai", "deepseek", "custom", "claude"]


@pytest.mark.asyncio
@pytest.mark.skip(reason="CatToken providers are retired from active settings")
async def test_existing_cattoken_record_uses_fixed_display_name_and_preserves_values(
    tmp_path,
):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.list_all.return_value = [
        provider_row(
            slug="cattoken",
            display_name="CatToken",
            default_model="historical-model",
            supported_models=["historical-model", "another-historical-model"],
            encrypted_api_key=crypto.encrypt("stored-test-key-A1B2"),
            api_key_last4="A1B2",
            is_enabled=True,
            last_test_status="success",
            last_test_message="Historical test result",
        )
    ]
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
    )

    result = await service.list_public()
    cattoken = next(item for item in result if item.slug == "cattoken")

    assert cattoken.display_name == "CatToken OpenAI"
    assert cattoken.masked_api_key == "••••A1B2"
    assert cattoken.default_model == "historical-model"
    assert cattoken.supported_models == [
        "historical-model",
        "another-historical-model",
    ]
    assert cattoken.last_test_status == "success"
    assert cattoken.last_test_message == "Historical test result"
    assert cattoken.is_enabled is True


@pytest.mark.asyncio
@pytest.mark.skip(reason="CatToken providers are retired from active settings")
async def test_existing_cattoken_claude_uses_fixed_protocol_and_preserves_its_values(
    tmp_path,
):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.list_all.return_value = [
        provider_row(
            slug="cattoken",
            encrypted_api_key=crypto.encrypt("stored-test-key-A1B2"),
            api_key_last4="A1B2",
            default_model="openai-historical-model",
            last_test_status="success",
        ),
        provider_row(
            slug="cattoken_claude",
            provider_type="anthropic",
            api_protocol="openai",
            display_name="CatToken Claude",
            encrypted_api_key=crypto.encrypt("stored-test-key-C3D4"),
            api_key_last4="C3D4",
            default_model="claude-historical-model",
            supported_models=["claude-historical-model"],
            is_enabled=True,
            last_test_status="success",
            last_test_message="Historical Claude test result",
        ),
    ]
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
    )

    result = await service.list_public()
    cattoken = next(item for item in result if item.slug == "cattoken")
    cattoken_claude = next(item for item in result if item.slug == "cattoken_claude")

    assert cattoken.api_protocol == "openai"
    assert cattoken.masked_api_key == "••••A1B2"
    assert cattoken.default_model == "openai-historical-model"
    assert cattoken.last_test_status == "success"
    assert cattoken_claude.api_protocol == "anthropic"
    assert cattoken_claude.masked_api_key == "••••C3D4"
    assert cattoken_claude.default_model == "claude-historical-model"
    assert cattoken_claude.supported_models == ["claude-historical-model"]
    assert cattoken_claude.last_test_status == "success"
    assert cattoken_claude.last_test_message == "Historical Claude test result"
    assert cattoken_claude.is_enabled is True


@pytest.mark.asyncio
async def test_save_does_not_call_provider_or_spend_tokens(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = provider_row(
        encrypted_api_key=crypto.encrypt("sk-old"),
        api_key_last4="-old",
        is_enabled=True,
    )
    repository.upsert.return_value = provider_row(
        default_model="gpt-4.1",
        encrypted_api_key=crypto.encrypt("sk-new"),
        api_key_last4="-new",
        is_enabled=True,
    )
    repository.list_model_validations.return_value = []
    tester = AsyncMock()
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=tester,
    )

    result = await service.save(
        "openai",
        ProviderUpdate(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4.1",
            api_key=SecretStr("sk-new"),
            is_enabled=True,
        ),
    )

    tester.assert_not_awaited()
    repository.upsert.assert_awaited_once()
    assert result.default_model == "gpt-4.1"


@pytest.mark.asyncio
async def test_save_with_the_same_api_key_preserves_model_validations(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = provider_row(
        encrypted_api_key=crypto.encrypt("same-test-key"),
        api_key_last4="-key",
        is_enabled=True,
        supported_models=["gpt-4o"],
        last_test_status="success",
    )
    repository.upsert.side_effect = lambda **values: provider_row(**values)
    repository.list_model_validations.return_value = []
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
    )

    result = await service.save(
        "openai",
        ProviderUpdate(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o",
            api_key=SecretStr("same-test-key"),
            is_enabled=True,
        ),
    )

    repository.delete_model_validations.assert_not_awaited()
    assert result.supported_models == ["gpt-4o"]
    assert result.last_test_status == "success"


@pytest.mark.asyncio
async def test_save_with_a_different_api_key_advances_revision_and_keeps_history(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = provider_row(
        encrypted_api_key=crypto.encrypt("old-test-key"),
        api_key_last4="-key",
        is_enabled=True,
        supported_models=["gpt-4o"],
        last_test_status="success",
    )
    repository.upsert.side_effect = lambda **values: provider_row(**values)
    repository.increment_validation_revision.return_value = provider_row(
        validation_revision=2
    )
    repository.list_model_validations.return_value = []
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
    )

    result = await service.save(
        "openai",
        ProviderUpdate(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o",
            api_key=SecretStr("new-test-key"),
            is_enabled=True,
        ),
    )

    repository.increment_validation_revision.assert_awaited_once_with("openai")
    repository.delete_model_validations.assert_not_awaited()
    assert result.supported_models == []
    assert result.last_test_status == "untested"


@pytest.mark.asyncio
async def test_failed_connection_test_invalidates_saved_model_catalog(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = provider_row(
        encrypted_api_key=crypto.encrypt("sk-old"),
        api_key_last4="-old",
        is_enabled=True,
        supported_models=["old-model"],
        last_test_status="success",
        last_test_message="Connection successful",
    )
    tester = AsyncMock(
        side_effect=ProviderConnectionError(
            code="PROVIDER_MODEL_INVALID",
            message="The configured model was not found or is unavailable",
            retryable=False,
        )
    )
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=tester,
    )

    with pytest.raises(ProviderConnectionError):
        await service.test_draft(
            "openai",
            ProviderDraft(
                base_url="https://api.openai.com/v1",
                default_model="missing-model",
            ),
        )

    persisted = repository.record_test_failure.await_args.kwargs
    assert persisted["slug"] == "openai"
    assert persisted["message"] == "The configured model was not found or is unavailable"


@pytest.mark.asyncio
async def test_successful_save_encrypts_secret_before_persistence(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = None

    async def return_saved(**values):
        return provider_row(**values)

    repository.upsert.side_effect = return_saved
    tester = AsyncMock(
        return_value=ProviderConnectionTestResult(
            message="Connection successful",
            models=("model-x", "model-y"),
        )
    )
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=tester,
    )

    result = await service.save(
        "custom",
        ProviderUpdate(
            api_protocol="anthropic",
            display_name="Internal API",
            base_url="https://llm.example/v1",
            default_model="model-x",
            api_key=SecretStr("custom-secret-99AA"),
            is_enabled=True,
        ),
    )

    persisted = repository.upsert.await_args.kwargs
    assert persisted["encrypted_api_key"] != "custom-secret-99AA"
    assert crypto.decrypt(persisted["encrypted_api_key"]) == "custom-secret-99AA"
    assert persisted["api_key_last4"] == "99AA"
    assert persisted["supported_models"] == []
    assert persisted["api_protocol"] == "anthropic"
    assert persisted["base_url"] == "https://llm.example"
    assert result.api_protocol == "anthropic"
    assert result.masked_api_key == "••••99AA"
    assert result.supported_models == []
    tester.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_normalizes_complete_anthropic_messages_url(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = None

    async def return_saved(**values):
        return provider_row(**values)

    repository.upsert.side_effect = return_saved
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
    )

    await service.save(
        "custom",
        ProviderUpdate(
            api_protocol="anthropic",
            display_name="Anthropic Gateway",
            base_url="https://llm.example/gateway/v1/messages?trace=1#result",
            default_model="claude-sonnet",
            api_key=SecretStr("custom-secret"),
            is_enabled=True,
        ),
    )

    assert repository.upsert.await_args.kwargs["base_url"] == (
        "https://llm.example/gateway"
    )


@pytest.mark.asyncio
async def test_save_normalizes_complete_openai_compatible_url(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.return_value = None

    async def return_saved(**values):
        return provider_row(**values)

    repository.upsert.side_effect = return_saved
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
    )

    await service.save(
        "custom",
        ProviderUpdate(
            api_protocol="openai",
            display_name="OpenAI Gateway",
            base_url="https://llm.example/gateway/v1/chat/completions?trace=1#result",
            default_model="gpt-5.6",
            api_key=SecretStr("custom-secret"),
            is_enabled=True,
        ),
    )

    assert repository.upsert.await_args.kwargs["base_url"] == (
        "https://llm.example/gateway/v1"
    )


@pytest.mark.asyncio
async def test_verify_model_persists_probe_and_sets_default_after_success(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    record = provider_row(
        slug="custom",
        api_protocol="anthropic",
        base_url="https://maike-ai.top",
        default_model="old-model",
        supported_models=["old-model", "claude-opus-5"],
        encrypted_api_key=crypto.encrypt("saved-secret"),
        is_enabled=True,
    )
    repository = AsyncMock()
    repository.get.return_value = record
    repository.upsert_model_validation.return_value = SimpleNamespace(
        provider_slug="custom",
        api_protocol="anthropic",
        model="claude-opus-5",
        status="verified",
        error_code=None,
        message="结构化验证成功",
        tested_at=datetime.now(timezone.utc),
    )
    verifier = AsyncMock(
        return_value=SimpleNamespace(
            model="claude-opus-5",
            status="verified",
            error_code=None,
            message="结构化验证成功",
        )
    )
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
        model_verifier=verifier,
    )

    result = await service.verify_model("custom", "claude-opus-5", set_default=True)

    assert (result.model, result.test_status) == ("claude-opus-5", "verified")
    repository.set_default_model.assert_awaited_once_with(
        "custom", "claude-opus-5"
    )
    verifier.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_custom_openai_persists_and_returns_capability_modes(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    record = provider_row(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="openai",
        base_url="https://proxy.example/v1",
        default_model="gpt-5.6",
        supported_models=["gpt-5.6"],
        encrypted_api_key=crypto.encrypt("saved-secret"),
        is_enabled=True,
        validation_revision=3,
    )
    repository = AsyncMock()
    repository.get.return_value = record
    verifier = AsyncMock(
        return_value=ProviderModelVerificationResult(
            model="gpt-5.6",
            status="verified",
            message="Structured validation succeeded",
            transport_mode="chat_completions",
            structured_output_mode="json_object",
        )
    )
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
        model_verifier=verifier,
    )

    result = await service.verify_model("custom", "gpt-5.6")

    assert result.transport_mode == "chat_completions"
    assert result.structured_output_mode == "json_object"
    persisted = repository.upsert_model_validation.await_args.kwargs
    assert persisted["connection_revision"] == 3
    assert persisted["transport_mode"] == "chat_completions"
    assert persisted["structured_output_mode"] == "json_object"


def test_public_custom_openai_exposes_modes_only_for_current_connection():
    record = provider_row(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="openai",
        display_name="OpenAI Gateway",
        base_url="https://proxy.example/v1",
        default_model="gpt-5.6",
        supported_models=["gpt-5.6", "gpt-5.5"],
        is_enabled=True,
        validation_revision=4,
    )
    validations = [
        SimpleNamespace(
            api_protocol="openai",
            model="gpt-5.6",
            status="verified",
            message="OK",
            error_code=None,
            tested_at=datetime.now(timezone.utc),
            connection_revision=4,
            transport_mode="chat_completions",
            structured_output_mode="json_schema",
        ),
        SimpleNamespace(
            api_protocol="openai",
            model="gpt-5.5",
            status="verified",
            message="old",
            error_code=None,
            tested_at=datetime.now(timezone.utc),
            connection_revision=3,
            transport_mode="responses",
            structured_output_mode="prompt_json",
        ),
    ]

    public = ProviderService._to_public("custom", record, validations)

    current, expired = public.model_options
    assert current.transport_mode == "chat_completions"
    assert current.structured_output_mode == "json_schema"
    assert expired.transport_mode is None
    assert expired.structured_output_mode is None


@pytest.mark.asyncio
async def test_select_model_requires_fresh_verified_validation(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    record = provider_row(
        slug="openai",
        api_protocol="openai",
        encrypted_api_key=crypto.encrypt("saved-secret"),
        is_enabled=True,
    )
    repository = AsyncMock()
    repository.get.return_value = record
    repository.list_model_validations.return_value = [
        SimpleNamespace(
            provider_slug="openai",
            api_protocol="openai",
            model="gpt-4o",
            status="verified",
            tested_at=datetime.now(timezone.utc) - timedelta(days=30),
            is_selected=False,
            connection_revision=1,
        )
    ]
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
    )

    result = await service.set_model_selected("openai", "gpt-4o", True)

    assert result.is_selected is True
    repository.set_model_selected.assert_awaited_once_with(
        "openai", "openai", "gpt-4o", True
    )


@pytest.mark.asyncio
async def test_select_model_rejects_unverified_model(tmp_path):
    repository = AsyncMock()
    repository.get.return_value = provider_row(
        slug="openai", api_protocol="openai", is_enabled=True
    )
    repository.list_model_validations.return_value = []
    service = ProviderService(
        repository=repository,
        crypto=ProviderCrypto(key_file=tmp_path / "provider.key"),
        connection_test=AsyncMock(),
    )

    with pytest.raises(ProviderConfigurationError) as exc_info:
        await service.set_model_selected("openai", "gpt-4o", True)

    assert exc_info.value.code == "PROVIDER_MODEL_NOT_VERIFIED"
    repository.set_model_selected.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_legacy_env_is_idempotent_and_never_overwrites_database(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    repository = AsyncMock()
    repository.get.side_effect = [None, provider_row(default_model="gpt-4.1")]
    service = ProviderService(
        repository=repository,
        crypto=crypto,
        connection_test=AsyncMock(),
    )
    legacy = SimpleNamespace(
        openai_api_key="sk-env",
        openai_model="gpt-4o",
        deepseek_api_key="",
        deepseek_model="deepseek-chat",
        deepseek_base_url="https://api.deepseek.com",
        cattoken_api_key="",
        cattoken_model="gpt-5.4",
        cattoken_base_url="https://www.cattoken.vip/v1",
    )

    await service.import_legacy_env(legacy)
    await service.import_legacy_env(legacy)

    assert repository.upsert.await_count == 1
    persisted = repository.upsert.await_args.kwargs
    assert crypto.decrypt(persisted["encrypted_api_key"]) == "sk-env"
    assert persisted["last_test_status"] == "untested"
    assert persisted["api_protocol"] == "openai"


@pytest.mark.asyncio
async def test_fixed_provider_rejects_anthropic_protocol(tmp_path):
    service = ProviderService(
        repository=AsyncMock(get=AsyncMock(return_value=None)),
        crypto=ProviderCrypto(key_file=tmp_path / "provider.key"),
        connection_test=AsyncMock(),
    )

    with pytest.raises(ProviderConfigurationError) as exc_info:
        await service.test_draft(
            "openai",
            ProviderDraft(
                api_protocol="anthropic",
                base_url="https://api.openai.com/v1",
                default_model="claude-sonnet",
                api_key=SecretStr("secret"),
            ),
        )

    assert exc_info.value.code == "PROVIDER_PROTOCOL_INVALID"


@pytest.mark.asyncio
@pytest.mark.skip(reason="CatToken providers are retired from active settings")
async def test_cattoken_claude_rejects_openai_protocol(tmp_path):
    service = ProviderService(
        repository=AsyncMock(get=AsyncMock(return_value=None)),
        crypto=ProviderCrypto(key_file=tmp_path / "provider.key"),
        connection_test=AsyncMock(),
    )

    with pytest.raises(ProviderConfigurationError) as exc_info:
        await service.test_draft(
            "cattoken_claude",
            ProviderDraft(
                api_protocol="openai",
                base_url="https://www.cattoken.vip",
                default_model="claude-sonnet-4-6",
                api_key=SecretStr("secret"),
            ),
        )

    assert exc_info.value.code == "PROVIDER_PROTOCOL_INVALID"
