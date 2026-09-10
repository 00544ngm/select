from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_backend_settings
from backend.db.models import User
from backend.db.session import get_session

PBKDF2_ITERATIONS = 210_000
PBKDF2_SALT_BYTES = 16


class AuthError(RuntimeError):
    """Raised when authentication is misconfigured or a credential is invalid."""


def hash_password(password: str, salt_b64: str | None = None) -> tuple[str, str]:
    """Return (password_hash, salt_b64) for a plaintext password."""
    if salt_b64:
        salt = base64.b64decode(salt_b64.encode("ascii"))
    else:
        salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
        salt_b64 = base64.b64encode(salt).decode("ascii")
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return base64.b64encode(digest).decode("ascii"), salt_b64


def verify_password(password: str, password_hash: str, salt_b64: str) -> bool:
    candidate, _ = hash_password(password, salt_b64)
    return hmac.compare_digest(candidate, password_hash)


def get_auth_secret() -> str:
    secret = get_backend_settings().auth_secret
    if not secret:
        raise AuthError("服务端未配置 AUTH_SECRET，请先在 .env 中设置。")
    return secret


def sign_token(*, sub: str, username: str, secret: str, ttl_seconds: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "username": username,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return ""


def _http_error(
    http_status: int, code: str, message: str, retryable: bool = False
) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message, "retryable": retryable},
    )


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Resolve the logged-in user from a Bearer token.

    Desktop (single-user local) mode has no login: returns ``None`` so callers
    may treat the local operator as unrestricted.
    """
    settings = get_backend_settings()
    if settings.runtime_mode == "desktop":
        return None

    token = bearer_token(request)
    if not token:
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "AUTH_REQUIRED", "未登录")

    try:
        secret = get_auth_secret()
    except AuthError as error:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_NOT_CONFIGURED",
            str(error),
        ) from error

    payload = decode_token(token, secret)
    if not payload or "sub" not in payload:
        raise _http_error(
            status.HTTP_401_UNAUTHORIZED, "AUTH_INVALID", "登录已失效，请重新登录"
        )

    try:
        user_id = UUID(str(payload["sub"]))
    except (ValueError, TypeError):
        raise _http_error(
            status.HTTP_401_UNAUTHORIZED, "AUTH_INVALID", "登录已失效，请重新登录"
        ) from None

    user = await session.get(User, user_id)
    if user is None:
        raise _http_error(
            status.HTTP_401_UNAUTHORIZED, "AUTH_INVALID", "登录已失效，请重新登录"
        )
    if user.status != "active":
        raise _http_error(
            status.HTTP_403_FORBIDDEN, "ACCOUNT_DISABLED", "账号已被禁用，请联系管理员"
        )
    return user


async def require_admin(
    user: User | None = Depends(get_current_user),
) -> User | None:
    if user is None:
        return None  # desktop single-user mode
    if user.role != "admin":
        raise _http_error(
            status.HTTP_403_FORBIDDEN, "ADMIN_ONLY", "仅管理员可执行此操作"
        )
    return user


__all__ = [
    "AuthError",
    "bearer_token",
    "decode_token",
    "get_auth_secret",
    "get_current_user",
    "hash_password",
    "require_admin",
    "sign_token",
    "verify_password",
]
