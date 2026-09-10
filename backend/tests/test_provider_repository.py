from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.base import Base
from backend.db.provider_repository import ProviderConfigurationRepository


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as current_session:
        yield current_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_repository_upserts_one_row_per_slug(session: AsyncSession):
    repository = ProviderConfigurationRepository(session)

    first = await repository.upsert(
        slug="openai",
        provider_type="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        supported_models=["gpt-4o", "gpt-4.1"],
        encrypted_api_key="cipher-1",
        api_key_last4="1111",
        is_enabled=True,
        last_test_status="success",
        last_test_message="Connection successful",
    )
    second = await repository.upsert(
        slug="openai",
        provider_type="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4.1",
        supported_models=["gpt-4.1"],
        encrypted_api_key="cipher-2",
        api_key_last4="2222",
        is_enabled=True,
        last_test_status="success",
        last_test_message="Connection successful",
    )

    assert first.id == second.id
    assert second.default_model == "gpt-4.1"
    assert second.supported_models == ["gpt-4.1"]
    assert second.api_key_last4 == "2222"
    assert len(await repository.list_all()) == 1


@pytest.mark.asyncio
async def test_provider_repository_get_returns_none_for_missing_slug(session: AsyncSession):
    repository = ProviderConfigurationRepository(session)

    assert await repository.get("custom") is None


@pytest.mark.asyncio
async def test_provider_repository_persists_api_protocol(session: AsyncSession):
    repository = ProviderConfigurationRepository(session)

    saved = await repository.upsert(
        slug="custom",
        provider_type="openai_compatible",
        api_protocol="anthropic",
        display_name="Anthropic Proxy",
        base_url="https://api.example.com",
        default_model="claude-sonnet",
        supported_models=["claude-sonnet"],
        encrypted_api_key="cipher",
        api_key_last4="1234",
        is_enabled=True,
        last_test_status="success",
        last_test_message="Connection successful",
    )

    assert saved.api_protocol == "anthropic"
    assert (await repository.get("custom")).api_protocol == "anthropic"


@pytest.mark.asyncio
async def test_provider_repository_clears_catalog_on_test_failure(session: AsyncSession):
    repository = ProviderConfigurationRepository(session)

    await repository.upsert(
        slug="custom",
        provider_type="openai_compatible",
        display_name="Custom API",
        base_url="https://api.example.com",
        default_model="model-x",
        supported_models=["model-x"],
        encrypted_api_key="cipher",
        api_key_last4="1234",
        is_enabled=True,
        last_test_status="success",
        last_test_message="Connection successful",
    )

    failed = await repository.record_test_failure(
        slug="custom",
        message="The configured model was not found or is unavailable",
        tested_at=datetime.now(timezone.utc),
    )

    assert failed is not None
    assert failed.supported_models == []
    assert failed.last_test_status == "failed"
    assert failed.last_test_message == "The configured model was not found or is unavailable"


@pytest.mark.asyncio
async def test_model_validations_are_independent_from_discovered_models(
    session: AsyncSession,
):
    repository = ProviderConfigurationRepository(session)
    tested_at = datetime.now(timezone.utc)

    await repository.upsert_model_validation(
        provider_slug="custom",
        api_protocol="anthropic",
        model="claude-opus-5",
        status="verified",
        error_code=None,
        message="结构化验证成功",
        tested_at=tested_at,
    )

    rows = await repository.list_model_validations("custom")
    assert [(row.model, row.status) for row in rows] == [
        ("claude-opus-5", "verified")
    ]

    assert await repository.delete_model_validations("custom") == 1
    assert await repository.list_model_validations("custom") == []


@pytest.mark.asyncio
async def test_repository_persists_openai_compatibility_modes(
    session: AsyncSession,
):
    repository = ProviderConfigurationRepository(session)

    saved = await repository.upsert_model_validation(
        provider_slug="custom",
        api_protocol="openai",
        model="gpt-5.6",
        status="verified",
        error_code=None,
        message="Structured validation succeeded",
        tested_at=datetime.now(timezone.utc),
        transport_mode="chat_completions",
        structured_output_mode="json_schema",
    )

    assert saved.transport_mode == "chat_completions"
    assert saved.structured_output_mode == "json_schema"
    rows = await repository.list_model_validations("custom")
    assert rows[0].transport_mode == "chat_completions"
    assert rows[0].structured_output_mode == "json_schema"


@pytest.mark.asyncio
async def test_repository_defaults_openai_compatibility_modes_to_none(
    session: AsyncSession,
):
    repository = ProviderConfigurationRepository(session)

    saved = await repository.upsert_model_validation(
        provider_slug="custom",
        api_protocol="anthropic",
        model="claude-sonnet",
        status="verified",
        error_code=None,
        message="Structured validation succeeded",
        tested_at=datetime.now(timezone.utc),
    )

    assert saved.transport_mode is None
    assert saved.structured_output_mode is None


@pytest.mark.asyncio
async def test_full_report_validation_preserves_openai_compatibility_modes(
    session: AsyncSession,
):
    repository = ProviderConfigurationRepository(session)
    tested_at = datetime.now(timezone.utc)
    await repository.upsert_model_validation(
        provider_slug="custom",
        api_protocol="openai",
        model="gpt-5.6",
        status="verified",
        error_code=None,
        message="Probe succeeded",
        tested_at=tested_at,
        transport_mode="chat_completions",
        structured_output_mode="prompt_json",
    )

    saved = await repository.record_full_report_validation(
        provider_slug="custom",
        api_protocol="openai",
        model="gpt-5.6",
        status="verified",
        error_code=None,
        message="Full report succeeded",
        tested_at=tested_at,
        connection_revision=1,
        schema_version="v2.1",
        quality_status="passed",
    )

    assert saved.transport_mode == "chat_completions"
    assert saved.structured_output_mode == "prompt_json"


@pytest.mark.asyncio
async def test_repository_tracks_connection_revision_and_model_usage(
    session: AsyncSession,
):
    repository = ProviderConfigurationRepository(session)
    provider = await repository.upsert(
        slug="openai",
        provider_type="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-5.6-sol",
        supported_models=["gpt-5.6-sol"],
        encrypted_api_key="cipher",
        api_key_last4="1234",
        is_enabled=True,
        last_test_status="success",
        last_test_message="Connection successful",
    )
    assert provider.validation_revision == 1

    tested_at = datetime.now(timezone.utc)
    validation = await repository.upsert_model_validation(
        provider_slug="openai",
        api_protocol="openai",
        model="gpt-5.6-sol",
        status="verified",
        error_code=None,
        message="结构化验证成功",
        tested_at=tested_at,
        connection_revision=provider.validation_revision,
        is_automatic=True,
    )
    assert validation.connection_revision == 1
    assert validation.last_auto_tested_at.replace(tzinfo=timezone.utc) == tested_at
    assert validation.use_count == 0
    assert validation.last_used_at is None

    used_at = datetime.now(timezone.utc)
    used = await repository.record_model_usage(
        "openai", "openai", "gpt-5.6-sol", used_at
    )
    assert used is not None
    assert used.use_count == 1
    assert used.last_used_at.replace(tzinfo=timezone.utc) == used_at

    incremented = await repository.increment_validation_revision("openai")
    assert incremented is not None
    assert incremented.validation_revision == 2
    history = await repository.list_model_validations("openai")
    assert len(history) == 1
    assert history[0].connection_revision == 1


@pytest.mark.asyncio
async def test_delete_exact_slugs_only_removes_retired_cattoken_records(session):
    repository = ProviderConfigurationRepository(session)
    for slug in ("openai", "cattoken", "cattoken_claude", "deepseek", "custom"):
        await repository.upsert(
            slug=slug,
            provider_type="openai",
            display_name=slug,
            base_url=None,
            default_model="model",
            supported_models=[],
            encrypted_api_key="ciphertext",
            api_key_last4="1234",
            is_enabled=True,
            last_test_status="untested",
            last_test_message=None,
        )

    assert await repository.delete_exact_slugs(
        frozenset({"cattoken", "cattoken_claude"})
    ) == 2
    assert [item.slug for item in await repository.list_all()] == [
        "openai",
        "deepseek",
        "custom",
    ]
    assert await repository.delete_exact_slugs(
        frozenset({"cattoken", "cattoken_claude"})
    ) == 0
