from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.dependencies import get_provider_service
from backend.api.schemas.providers import ProviderModelVerifyResult, ProviderPublic
from backend.application.provider_clients import ProviderConnectionTestResult
from backend.main import create_app
from backend.security.auth import require_admin


def public_provider() -> ProviderPublic:
    return ProviderPublic(
        slug="openai",
        api_protocol="openai",
        display_name="OpenAI",
        role="primary",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        supported_models=["gpt-4o", "gpt-4.1"],
        is_enabled=True,
        configured=True,
        masked_api_key="••••4F2A",
        last_test_status="success",
        last_tested_at=None,
        last_test_message="Connection successful",
    )


@pytest.mark.asyncio
async def test_provider_list_never_returns_secret():
    service = AsyncMock()
    service.list_public.return_value = [public_provider()]
    app = create_app()
    app.dependency_overrides[get_provider_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/api/v1/settings/providers")

    assert response.status_code == 200
    assert response.json()[0]["masked_api_key"] == "••••4F2A"
    assert response.json()[0]["api_protocol"] == "openai"
    assert response.json()[0]["model_options"][0] == {
        "provider": "openai",
        "provider_display_name": "OpenAI",
        "api_protocol": "openai",
        "model": "gpt-4o",
        "is_default": True,
        "is_selected": False,
        "is_enabled": True,
        "test_status": "discovered",
        "tested_at": None,
        "test_message": "目录发现，尚未真实验证",
        "error_code": None,
        "connection_revision": 1,
        "current_connection_revision": 1,
        "is_current_connection": True,
        "last_used_at": None,
        "use_count": 0,
        "last_auto_tested_at": None,
        "transport_mode": None,
        "structured_output_mode": None,
    }
    assert "encrypted_api_key" not in response.text
    assert "sk-" not in response.text


@pytest.mark.asyncio
@pytest.mark.skip(reason="CatToken providers are retired")
async def test_provider_test_returns_discovered_models():
    service = AsyncMock()
    service.test_draft.return_value = ProviderConnectionTestResult(
        message="Connection successful",
        models=("gpt-5.4", "gpt-5.5"),
    )
    app = create_app()
    app.dependency_overrides[get_provider_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.post(
            "/api/v1/settings/providers/cattoken/test",
            json={
                "base_url": "https://www.cattoken.vip/v1",
                "default_model": "gpt-5.4",
            },
        )

    assert response.status_code == 200
    assert response.json()["models"] == ["gpt-5.4", "gpt-5.5"]


@pytest.mark.asyncio
@pytest.mark.skip(reason="CatToken providers are retired")
async def test_provider_test_accepts_anthropic_protocol_for_cattoken_claude():
    service = AsyncMock()
    service.test_draft.return_value = ProviderConnectionTestResult(
        message="Connection successful",
        models=("claude-sonnet-4-6",),
    )
    app = create_app()
    app.dependency_overrides[get_provider_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.post(
            "/api/v1/settings/providers/cattoken_claude/test",
            json={
                "api_protocol": "anthropic",
                "base_url": "https://www.cattoken.vip",
                "default_model": "claude-sonnet-4-6",
            },
        )

    assert response.status_code == 200
    assert service.test_draft.await_args.args[0] == "cattoken_claude"
    assert service.test_draft.await_args.args[1].api_protocol == "anthropic"


@pytest.mark.asyncio
async def test_provider_test_accepts_anthropic_protocol_for_custom_provider():
    service = AsyncMock()
    service.test_draft.return_value = ProviderConnectionTestResult(
        message="Connection successful",
        models=("claude-sonnet",),
    )
    app = create_app()
    app.dependency_overrides[get_provider_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.post(
            "/api/v1/settings/providers/custom/test",
            json={
                "api_protocol": "anthropic",
                "base_url": "https://api.example.com",
                "default_model": "claude-sonnet",
                "api_key": "secret",
            },
        )

    assert response.status_code == 200
    draft = service.test_draft.await_args.args[1]
    assert draft.api_protocol == "anthropic"


@pytest.mark.asyncio
async def test_provider_settings_reject_non_loopback_clients():
    service = AsyncMock()
    app = create_app()
    app.dependency_overrides[get_provider_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: None

    transport = ASGITransport(app=app, client=("203.0.113.8", 32000))
    async with AsyncClient(transport=transport, base_url="http://example.com") as client:
        response = await client.get("/api/v1/settings/providers")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "SETTINGS_LOCAL_ONLY"
    service.list_public.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_model_verify_endpoint_returns_per_model_status():
    service = AsyncMock()
    service.verify_model.return_value = ProviderModelVerifyResult(
        provider="custom",
        model="claude-opus-5",
        test_status="verified",
        tested_at="2026-08-01T04:00:00Z",
        test_message="结构化验证成功",
        is_default=True,
        transport_mode="chat_completions",
        structured_output_mode="json_object",
    )
    app = create_app()
    app.dependency_overrides[get_provider_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.post(
            "/api/v1/settings/providers/custom/models/verify",
            json={
                "model": "claude-opus-5",
                "set_default": True,
                "is_automatic": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["test_status"] == "verified"
    assert response.json()["transport_mode"] == "chat_completions"
    assert response.json()["structured_output_mode"] == "json_object"
    service.verify_model.assert_awaited_once_with(
        "custom", "claude-opus-5", set_default=True, is_automatic=True
    )


@pytest.mark.asyncio
async def test_provider_model_selection_endpoint_updates_single_model():
    service = AsyncMock()
    service.set_model_selected.return_value = {
        "provider": "openai",
        "model": "gpt-4o",
        "is_selected": True,
    }
    app = create_app()
    app.dependency_overrides[get_provider_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.patch(
            "/api/v1/settings/providers/openai/models/gpt-4o/selection",
            json={"is_selected": True},
        )

    assert response.status_code == 200
    assert response.json()["is_selected"] is True
    service.set_model_selected.assert_awaited_once_with("openai", "gpt-4o", True)
