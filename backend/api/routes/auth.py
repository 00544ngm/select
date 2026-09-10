from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.dependencies import get_user_repository
from backend.api.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    UserPublic,
)
from backend.config import get_backend_settings
from backend.db.auth_repository import UserRepository
from backend.db.models import User
from backend.security.auth import (
    AuthError,
    get_auth_secret,
    get_current_user,
    hash_password,
    sign_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

USERNAME_PATTERN = r"^[a-z0-9_-]{2,32}$"


def _public(user: User) -> UserPublic:
    return UserPublic(
        id=str(user.id),
        username=user.username,
        role=user.role,
        status=user.status,
        full_name=user.full_name,
        api_group_id=str(user.api_group_id) if user.api_group_id else None,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    repository: UserRepository = Depends(get_user_repository),
) -> LoginResponse:
    username = body.username.strip().lower()
    user = await repository.get_by_username(username)
    if user is None or not verify_password(
        body.password, user.password_hash, user.password_salt
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_INVALID_CREDENTIALS",
                "message": "用户名或密码不正确",
                "retryable": False,
            },
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCOUNT_DISABLED",
                "message": "账号已被禁用，请联系管理员",
                "retryable": False,
            },
        )

    try:
        secret = get_auth_secret()
    except AuthError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AUTH_NOT_CONFIGURED",
                "message": str(error),
                "retryable": False,
            },
        ) from error

    token = sign_token(
        sub=str(user.id),
        username=user.username,
        secret=secret,
        ttl_seconds=get_backend_settings().auth_token_ttl_seconds,
    )
    return LoginResponse(access_token=token, user=_public(user))


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user=_public(user))


@router.post("/change-password", response_model=MeResponse)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    repository: UserRepository = Depends(get_user_repository),
) -> MeResponse:
    if not user.must_change_password:
        if not body.current_password or not verify_password(
            body.current_password, user.password_hash, user.password_salt
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "AUTH_WRONG_PASSWORD",
                    "message": "当前密码不正确",
                    "retryable": False,
                },
            )

    password_hash, password_salt = hash_password(body.new_password)
    user.password_hash = password_hash
    user.password_salt = password_salt
    user.must_change_password = False
    user = await repository.save(user)
    return MeResponse(user=_public(user))


__all__ = ["router"]
