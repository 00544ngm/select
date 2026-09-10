from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.routes.health import (
    check_database,
    check_desktop_runtime,
    check_redis,
    check_worker,
    check_worker_identity,
)
from backend.config import get_backend_settings
from backend.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_readiness_checks_database(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code in (200, 503)
    data = response.json()
    assert "database" in data
    assert data["database"] in ("ok", "unavailable")


@pytest.mark.asyncio
async def test_readiness_checks_redis(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code in (200, 503)
    data = response.json()
    assert "redis" in data
    assert data["redis"] in ("ok", "unavailable")


@pytest.mark.asyncio
async def test_readiness_checks_worker(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code in (200, 503)
    data = response.json()
    assert "worker" in data
    assert data["worker"] in ("ok", "unavailable")


@pytest.mark.asyncio
async def test_readiness_overall_failure_when_any_probe_fails(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code in (200, 503)


@pytest.mark.asyncio
async def test_liveness_still_works(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def _ready_response(app, *, identity, database="ok", redis="ok", worker="ok", runtime="ok"):
    app.dependency_overrides[check_database] = lambda: database
    app.dependency_overrides[check_redis] = lambda: redis
    app.dependency_overrides[check_worker] = lambda: worker
    app.dependency_overrides[check_worker_identity] = lambda: identity
    app.dependency_overrides[check_desktop_runtime] = lambda: runtime
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_readiness_reports_matching_runtime_contract(app, monkeypatch):
    monkeypatch.setattr(
        "backend.api.routes.health.runtime_revision",
        lambda: "revision-123",
    )
    response = await _ready_response(
        app,
        identity={
            "model_version": "combination_model_v2.1",
            "revision": "revision-123",
            "started_at": "2026-07-30T00:00:00+00:00",
            "worker_id": "worker-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["api_model_version"] == "combination_model_v2.1"
    assert data["worker_model_version"] == "combination_model_v2.1"
    assert data["api_revision"] == "revision-123"
    assert data["worker_revision"] == "revision-123"
    assert data["contract_match"] == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity",
    [
        None,
        {"model_version": "combination_model_v2.0", "revision": "revision-123"},
        {"model_version": "combination_model_v2.1", "revision": "old-revision"},
    ],
)
async def test_readiness_rejects_missing_or_mismatched_worker_identity(
    app, monkeypatch, identity
):
    monkeypatch.setattr(
        "backend.api.routes.health.runtime_revision",
        lambda: "revision-123",
    )
    response = await _ready_response(app, identity=identity)

    assert response.status_code == 503
    assert response.json()["contract_match"] in {"mismatch", "unavailable"}


@pytest.mark.asyncio
async def test_readiness_allows_unknown_revision_when_versions_match(app, monkeypatch):
    monkeypatch.setattr(
        "backend.api.routes.health.runtime_revision",
        lambda: "unknown",
    )
    response = await _ready_response(
        app,
        identity={
            "model_version": "combination_model_v2.1",
            "revision": "revision-123",
        },
    )

    assert response.status_code == 200
    assert response.json()["contract_match"] == "ok"
    assert response.json()["api_revision"] == "unknown"


@pytest.mark.asyncio
async def test_desktop_readiness_reports_queue_without_redis(app, monkeypatch):
    monkeypatch.setenv("RUNTIME_MODE", "desktop")
    get_backend_settings.cache_clear()
    try:
        response = await _ready_response(
            app,
            identity={
                "model_version": "combination_model_v2.1",
                "revision": "unknown",
            },
        )
    finally:
        get_backend_settings.cache_clear()

    assert response.status_code == 200
    assert response.json()["queue"] == "ok"
    assert "redis" not in response.json()


@pytest.mark.asyncio
async def test_desktop_runtime_probe_rejects_missing_packaged_browser(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_MODE", "desktop")
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "员工 #100%" / "artifacts"))
    monkeypatch.setenv("DESKTOP_BROWSER_EXECUTABLE", str(tmp_path / "missing.exe"))
    monkeypatch.setattr(
        "backend.desktop.browser_paths._default_edge_paths", list
    )
    get_backend_settings.cache_clear()
    try:
        assert await check_desktop_runtime() == "unavailable"
    finally:
        get_backend_settings.cache_clear()


@pytest.mark.asyncio
async def test_desktop_runtime_accepts_edge_when_bundled_browser_is_missing(
    monkeypatch, tmp_path
):
    edge = tmp_path / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.touch()
    monkeypatch.setenv("RUNTIME_MODE", "desktop")
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "employee" / "artifacts"))
    monkeypatch.setenv("DESKTOP_BROWSER_EXECUTABLE", str(tmp_path / "missing.exe"))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path))
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    get_backend_settings.cache_clear()
    try:
        assert await check_desktop_runtime() == "ok"
    finally:
        get_backend_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable_dependency", ["database", "redis", "worker"])
async def test_readiness_returns_503_for_each_unavailable_dependency(
    app, monkeypatch, unavailable_dependency
):
    monkeypatch.setattr(
        "backend.api.routes.health.runtime_revision",
        lambda: "revision-123",
    )
    dependencies = {"database": "ok", "redis": "ok", "worker": "ok"}
    dependencies[unavailable_dependency] = "unavailable"

    response = await _ready_response(
        app,
        identity={
            "model_version": "combination_model_v2.1",
            "revision": "revision-123",
        },
        **dependencies,
    )

    assert response.status_code == 503
    assert response.json()[unavailable_dependency] == "unavailable"
    assert response.json()["contract_match"] == "ok"
