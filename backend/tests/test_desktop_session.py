from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import BackendSettings
from backend.main import create_app


def desktop_app():
    return create_app(
        BackendSettings(
            runtime_mode="desktop",
            desktop_session_token="test-session",
            _env_file=None,
        )
    )


@pytest.mark.asyncio
async def test_desktop_api_rejects_missing_session_header() -> None:
    transport = ASGITransport(app=desktop_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/jobs")
        live = await client.get("/api/v1/health/live")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "DESKTOP_SESSION_REQUIRED"
    assert live.status_code == 200


@pytest.mark.asyncio
async def test_desktop_api_accepts_matching_session_header() -> None:
    transport = ASGITransport(app=desktop_app())
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Desktop-Session": "test-session"},
    ) as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code in {200, 503}


@pytest.mark.asyncio
async def test_server_mode_does_not_require_desktop_session() -> None:
    app = create_app(BackendSettings(runtime_mode="server", _env_file=None))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
