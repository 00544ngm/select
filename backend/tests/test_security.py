from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from backend.logging import RequestIDFilter
from backend.api.dependencies import get_job_queue
from backend.main import create_app


@pytest.fixture
def app():
    application = create_app()
    # /jobs, /search are login-gated in server mode; this module does not test
    # auth, so resolve auth/group dependencies to inert stubs.
    from backend.api.dependencies import get_api_group_repository
    from backend.security.auth import get_current_user

    application.dependency_overrides[get_current_user] = lambda: None
    application.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    return application


@pytest.mark.asyncio
async def test_cors_rejects_unknown_origin(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/health/live",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.asyncio
async def test_cors_allows_configured_origin(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/health/live",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_allows_local_dev_port(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/health/live",
            headers={
                "Origin": "http://localhost:57237",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:57237"


@pytest.mark.asyncio
async def test_cors_preflight_allows_authorization_header(app):
    """Bearer auth must pass its CORS preflight (regression: Authorization was
    missing from allow_headers, so every authenticated browser request failed
    with 'Response to preflight request doesn't pass access control check')."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/health/live",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    allow_headers = response.headers.get("Access-Control-Allow-Headers", "").lower()
    assert "authorization" in allow_headers


@pytest.mark.asyncio
async def test_cors_preflight_allows_delete_method(app):
    """Admin group/user deletion uses DELETE, which must be in allow_methods
    (regression: DELETE was absent, so the admin page could not remove rows)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/health/live",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "DELETE",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    assert "DELETE" in response.headers.get("Access-Control-Allow-Methods", "")


@pytest.mark.asyncio
async def test_cors_allows_private_network_lan_origin(app):
    """Server-mode console must be reachable from other machines on the LAN
    (regression: origins outside localhost were rejected, blocking login)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/health/live",
            headers={
                "Origin": "http://192.168.1.50:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "http://192.168.1.50:3000"


@pytest.mark.asyncio
async def test_error_response_has_stable_format(app):
    """Validation errors (no DB needed) return {code, message, retryable} format."""
    app.dependency_overrides[get_job_queue] = lambda: AsyncMock()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/jobs/hypothesis",
                json={"url": "not-a-valid-url"},
            )
    finally:
        app.dependency_overrides.pop(get_job_queue, None)

    assert response.status_code == 422
    body = response.json()
    detail = body["detail"]
    assert isinstance(detail, dict)
    assert "code" in detail
    assert "message" in detail
    assert "retryable" in detail
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_unhandled_exception_omits_sensitive_data(app):
    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("API_KEY=sk-abc123 and /home/user/.env")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/crash")

    assert response.status_code == 500
    body = response.json()
    detail = body["detail"]
    assert detail["code"] == "INTERNAL_ERROR"
    assert detail["message"] == "An unexpected error occurred"
    assert detail["retryable"] is True
    assert "sk-abc123" not in response.text
    assert "Traceback" not in response.text
    assert "/home/user/" not in response.text


@pytest.mark.asyncio
async def test_response_includes_request_id(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")

    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


def test_request_id_filter_supplies_default_for_background_logs():
    record = logging.LogRecord(
        name="worker", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="background failure", args=(), exc_info=None,
    )

    assert RequestIDFilter().filter(record) is True
    assert record.request_id == "-"
