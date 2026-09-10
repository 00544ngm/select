from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.dependencies import get_user_repository
from backend.config import get_backend_settings
from backend.db.models import User
from backend.main import create_app
from backend.security.auth import get_current_user, hash_password


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_user(*, role: str = "admin", status: str = "active") -> User:
    return User(
        id=uuid4(),
        username="admin" if role == "admin" else "employee",
        password_hash="h",
        password_salt="s",
        role=role,
        status=status,
        full_name=None,
        api_group_id=None,
        must_change_password=False,
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.fixture
def auth_configured(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    get_backend_settings.cache_clear()
    yield
    get_backend_settings.cache_clear()


def _client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://127.0.0.1")


@pytest.mark.asyncio
async def test_login_returns_token_and_user(auth_configured):
    digest, salt = hash_password("correct-password")
    user = make_user(role="admin")
    user.password_hash = digest
    user.password_salt = salt

    repository = AsyncMock()
    repository.get_by_username.return_value = user

    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: repository

    async with _client(app) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "Admin", "password": "correct-password"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "admin"
    repository.get_by_username.assert_awaited_once_with("admin")


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(auth_configured):
    digest, salt = hash_password("correct-password")
    user = make_user(role="admin")
    user.password_hash = digest
    user.password_salt = salt

    repository = AsyncMock()
    repository.get_by_username.return_value = user

    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: repository

    async with _client(app) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_me_requires_token():
    app = create_app()
    async with _client(app) as client:
        response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_admin_routes_reject_employee():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: make_user(
        role="employee", status="active"
    )
    async with _client(app) as client:
        response = await client.get("/api/v1/admin/users")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ADMIN_ONLY"
