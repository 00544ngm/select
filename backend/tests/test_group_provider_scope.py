"""Regression tests for ApiGroup-scoped provider engine + submit gate.

Covers (1) group config/validation/usage isolation, (2) job submission being
gated against the submitter's OWN group rows (never the global set), and
(3) group-scoped resolver refusing to fall back to legacy env credentials.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api.schemas.jobs import HypothesisJobCreate
from backend.api.schemas.providers import ProviderUpdate
from backend.application.job_service import JobService
from backend.application.provider_clients import ProviderClientResolver
from backend.application.provider_service import ProviderService
from backend.application.errors import ServiceUnavailableError
from backend.db.base import Base
from backend.db.models import ApiGroup
from backend.db.provider_repository import GroupProviderRepository


class FakeCrypto:
    def encrypt(self, value: str) -> str:
        return "enc::" + value

    def decrypt(self, value: str) -> str:
        return value[len("enc::"):]

    def mask(self, value: str | None) -> str | None:
        return value[-4:] if value and len(value) >= 4 else None


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as current_session:
        yield current_session
    await engine.dispose()


async def _make_groups(session: AsyncSession) -> tuple[str, str]:
    group_a = ApiGroup(name=f"grp-a-{uuid4().hex[:6]}", status="active")
    group_b = ApiGroup(name=f"grp-b-{uuid4().hex[:6]}", status="active")
    session.add_all([group_a, group_b])
    await session.commit()
    await session.refresh(group_a)
    await session.refresh(group_b)
    return str(group_a.id), str(group_b.id)


@pytest.mark.asyncio
async def test_group_repository_isolates_configs_validations_and_usage(
    session: AsyncSession,
) -> None:
    group_a, group_b = await _make_groups(session)
    repo_a = GroupProviderRepository(session, api_group_id=UUID(group_a))
    repo_b = GroupProviderRepository(session, api_group_id=UUID(group_b))
    service_a = ProviderService(repository=repo_a, crypto=FakeCrypto(), connection_test=None)

    await service_a.save(
        "custom",
        ProviderUpdate(
            base_url="https://grp-a.example/v1",
            api_key="sk-AAAA",
            default_model="m-a",
            is_enabled=True,
            api_protocol="openai",
        ),
    )

    row_a = await repo_a.get("custom")
    row_b = await repo_b.get("custom")
    assert row_a is not None and row_a.base_url == "https://grp-a.example/v1"
    assert row_b is None  # config never leaks to sibling group

    await repo_a.upsert_model_validation(
        provider_slug="custom",
        api_protocol="openai",
        model="m-a",
        status="verified",
        error_code=None,
        message="ok",
        tested_at=datetime.now(timezone.utc),
        connection_revision=1,
    )
    assert await repo_a.get_model_validation("custom", "openai", "m-a") is not None
    assert await repo_b.get_model_validation("custom", "openai", "m-a") is None

    used_a = await repo_a.record_model_usage("custom", "openai", "m-a", datetime.now(timezone.utc))
    used_b = await repo_b.record_model_usage("custom", "openai", "m-a", datetime.now(timezone.utc))
    assert used_a is not None and used_a.use_count == 1
    assert used_b is None


@pytest.mark.asyncio
async def test_submit_gate_uses_group_scope_and_never_global(session: AsyncSession) -> None:
    group_a, _ = await _make_groups(session)
    repo_a = GroupProviderRepository(session, api_group_id=UUID(group_a))

    def make_service() -> ProviderService:
        return ProviderService(repository=repo_a, crypto=FakeCrypto(), connection_test=None)

    async def scope_available(provider: str, model: str | None, scope: str) -> bool:
        return await make_service().is_model_available(provider, model)

    job_writer = AsyncMock()
    job_writer.create.return_value = SimpleNamespace(id=uuid4())
    queue = AsyncMock()
    service = JobService(
        repository=job_writer,
        queue=queue,
        provider_available=None,
        model_used=None,
        scope_provider_available=scope_available,
        scope_model_used=None,
    )

    # (a) group has NO verified model yet -> global gpt-4o must NOT be accepted
    request = HypothesisJobCreate(
        url="https://www.walmart.com/ip/Test/123",
        provider="custom",
        model="m-a",
    )
    with pytest.raises(ServiceUnavailableError) as excinfo:
        await service.submit_hypothesis(request, api_group_id=group_a)
    assert excinfo.value.code == "PROVIDER_MODEL_NOT_VERIFIED"
    job_writer.create.assert_not_awaited()

    # (b) configure group + verify & select its own model -> now accepted and the
    #     api_group_id is persisted onto the payload for the worker to replay.
    await repo_a.upsert(
        slug="custom",
        provider_type="custom",
        display_name="Custom",
        base_url="https://grp-a.example/v1",
        default_model="m-a",
        supported_models=["m-a"],
        encrypted_api_key=FakeCrypto().encrypt("sk-AAAA"),
        api_key_last4="AAAA",
        is_enabled=True,
        last_test_status="success",
        last_test_message="ok",
        api_protocol="openai",
    )
    await repo_a.upsert_model_validation(
        provider_slug="custom",
        api_protocol="openai",
        model="m-a",
        status="verified",
        error_code=None,
        message="ok",
        tested_at=datetime.now(timezone.utc),
        connection_revision=1,
        is_automatic=False,
    )
    await repo_a.set_model_selected("custom", "openai", "m-a", True)

    await service.submit_hypothesis(request, api_group_id=group_a)
    job_writer.create.assert_awaited_once()
    payload = job_writer.create.await_args.kwargs["request_payload"]
    assert payload["api_group_id"] == group_a


@pytest.mark.asyncio
async def test_group_resolver_never_falls_back_to_legacy_env(session: AsyncSession) -> None:
    group_a, _ = await _make_groups(session)
    repo = GroupProviderRepository(session, api_group_id=UUID(group_a))
    resolver = ProviderClientResolver(
        repository=repo,
        crypto=FakeCrypto(),
        legacy_settings=SimpleNamespace(openai_api_key="legacy-openai-key"),
        group_scoped=True,
    )
    from backend.application.provider_clients import ProviderResolutionError

    with pytest.raises(ProviderResolutionError) as excinfo:
        await resolver.resolve_primary("openai", "gpt-4o")
    assert excinfo.value.code == "PROVIDER_NOT_CONFIGURED"
