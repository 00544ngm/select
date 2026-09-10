from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.dependencies import (
    get_api_group_repository,
    get_provider_crypto,
    get_user_repository,
)
from backend.api.schemas.admin import (
    AdminUserPublic,
    ApiGroupCreate,
    ApiGroupPublic,
    ApiGroupUpdate,
    ResetPasswordRequest,
    UserCreate,
    UserUpdate,
)
from backend.db.auth_repository import ApiGroupRepository, UserRepository
from backend.db.models import ApiGroup, User
from backend.security.auth import hash_password, require_admin
from backend.security.provider_crypto import ProviderCrypto

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)

USERNAME_PATTERN = re.compile(r"^[a-z0-9_-]{2,32}$")


def _http(
    http_status: int, code: str, message: str, retryable: bool = False
) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message, "retryable": retryable},
    )


def _mask_key(last4: str | None) -> str | None:
    if not last4:
        return None
    return f"••••{last4}"


def _group_public(group: ApiGroup, member_count: int = 0) -> ApiGroupPublic:
    return ApiGroupPublic(
        id=str(group.id),
        name=group.name,
        status=group.status,
        note=group.note,
        base_url=group.base_url,
        masked_api_key=_mask_key(group.api_key_last4),
        default_model=group.default_model,
        supported_models=group.supported_models,
        member_count=member_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def _user_public(user: User) -> AdminUserPublic:
    return AdminUserPublic(
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


# --- API groups ---


@router.get("/api-groups", response_model=list[ApiGroupPublic])
async def list_api_groups(
    groups: ApiGroupRepository = Depends(get_api_group_repository),
    users: UserRepository = Depends(get_user_repository),
) -> list[ApiGroupPublic]:
    all_groups = await groups.list_all()
    counts: dict[UUID, int] = {}
    for user in await users.list_all():
        if user.api_group_id is not None:
            counts[user.api_group_id] = counts.get(user.api_group_id, 0) + 1
    return [_group_public(group, counts.get(group.id, 0)) for group in all_groups]


@router.post("/api-groups", response_model=ApiGroupPublic)
async def create_api_group(
    body: ApiGroupCreate,
    groups: ApiGroupRepository = Depends(get_api_group_repository),
    crypto: ProviderCrypto = Depends(get_provider_crypto),
    admin: User | None = Depends(require_admin),
) -> ApiGroupPublic:
    api_key = body.api_key.get_secret_value() if body.api_key else None
    group = ApiGroup(
        name=body.name.strip(),
        status="active",
        note=body.note,
        base_url=body.base_url,
        encrypted_api_key=crypto.encrypt(api_key) if api_key else None,
        api_key_last4=api_key[-4:] if api_key else None,
        default_model=body.default_model,
        supported_models=body.supported_models,
        created_by=admin.id if admin else None,
        updated_by=admin.id if admin else None,
    )
    group = await groups.add(group)
    return _group_public(group)


@router.put("/api-groups/{group_id}", response_model=ApiGroupPublic)
async def update_api_group(
    group_id: UUID,
    body: ApiGroupUpdate,
    groups: ApiGroupRepository = Depends(get_api_group_repository),
    crypto: ProviderCrypto = Depends(get_provider_crypto),
    admin: User | None = Depends(require_admin),
) -> ApiGroupPublic:
    group = await groups.get(group_id)
    if group is None:
        raise _http(status.HTTP_404_NOT_FOUND, "GROUP_NOT_FOUND", "接口组不存在")

    if body.name is not None:
        group.name = body.name.strip()
    if body.status is not None:
        group.status = body.status
    if body.note is not None:
        group.note = body.note
    if body.base_url is not None:
        group.base_url = body.base_url
    if body.default_model is not None:
        group.default_model = body.default_model
    if body.supported_models is not None:
        group.supported_models = body.supported_models
    if body.clear_api_key:
        group.encrypted_api_key = None
        group.api_key_last4 = None
    elif body.api_key is not None:
        api_key = body.api_key.get_secret_value()
        group.encrypted_api_key = crypto.encrypt(api_key)
        group.api_key_last4 = api_key[-4:]
    group.updated_by = admin.id if admin else None

    group = await groups.save(group)
    return _group_public(group)


@router.delete("/api-groups/{group_id}")
async def disable_api_group(
    group_id: UUID,
    groups: ApiGroupRepository = Depends(get_api_group_repository),
) -> dict[str, bool]:
    group = await groups.get(group_id)
    if group is None:
        raise _http(status.HTTP_404_NOT_FOUND, "GROUP_NOT_FOUND", "接口组不存在")
    group.status = "disabled"
    await groups.save(group)
    return {"ok": True}


# --- Users ---


@router.get("/users", response_model=list[AdminUserPublic])
async def list_users(
    users: UserRepository = Depends(get_user_repository),
) -> list[AdminUserPublic]:
    return [_user_public(user) for user in await users.list_all()]


@router.post("/users", response_model=AdminUserPublic)
async def create_user(
    body: UserCreate,
    users: UserRepository = Depends(get_user_repository),
    groups: ApiGroupRepository = Depends(get_api_group_repository),
) -> AdminUserPublic:
    username = body.username.strip().lower()
    if not USERNAME_PATTERN.match(username):
        raise _http(
            status.HTTP_400_BAD_REQUEST,
            "USERNAME_INVALID",
            "用户名只能包含小写字母、数字、下划线或短横线，长度 2-32 位",
        )
    if await users.get_by_username(username) is not None:
        raise _http(
            status.HTTP_409_CONFLICT,
            "USERNAME_TAKEN",
            "这个用户名已经存在，请换一个用户名",
        )
    api_group_id = UUID(body.api_group_id) if body.api_group_id else None
    if api_group_id is not None and await groups.get(api_group_id) is None:
        raise _http(status.HTTP_400_BAD_REQUEST, "GROUP_NOT_FOUND", "选择的接口组不存在")

    password_hash, password_salt = hash_password(body.password)
    user = User(
        username=username,
        password_hash=password_hash,
        password_salt=password_salt,
        role=body.role,
        status=body.status,
        full_name=body.full_name,
        api_group_id=api_group_id,
        must_change_password=True,
    )
    user = await users.add(user)
    return _user_public(user)


@router.put("/users/{user_id}", response_model=AdminUserPublic)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    users: UserRepository = Depends(get_user_repository),
    groups: ApiGroupRepository = Depends(get_api_group_repository),
    admin: User | None = Depends(require_admin),
) -> AdminUserPublic:
    user = await users.get(user_id)
    if user is None:
        raise _http(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "成员不存在")

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.status is not None:
        user.status = body.status
    if body.api_group_id is not None:
        api_group_id = UUID(body.api_group_id)
        if await groups.get(api_group_id) is None:
            raise _http(
                status.HTTP_400_BAD_REQUEST, "GROUP_NOT_FOUND", "选择的接口组不存在"
            )
        user.api_group_id = api_group_id

    # 防止把最后一个 active admin 降级/禁用，导致后台锁死。
    if (
        admin is not None
        and user.id == admin.id
        and (user.role != "admin" or user.status != "active")
    ):
        raise _http(
            status.HTTP_400_BAD_REQUEST,
            "ADMIN_LOCKOUT",
            "不能禁用或降级当前登录的管理员自己",
        )

    user = await users.save(user)
    return _user_public(user)


@router.post("/users/{user_id}/reset-password", response_model=AdminUserPublic)
async def reset_user_password(
    user_id: UUID,
    body: ResetPasswordRequest,
    users: UserRepository = Depends(get_user_repository),
) -> AdminUserPublic:
    user = await users.get(user_id)
    if user is None:
        raise _http(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "成员不存在")
    password_hash, password_salt = hash_password(body.new_password)
    user.password_hash = password_hash
    user.password_salt = password_salt
    user.must_change_password = True
    user = await users.save(user)
    return _user_public(user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    users: UserRepository = Depends(get_user_repository),
    admin: User | None = Depends(require_admin),
) -> dict[str, bool]:
    user = await users.get(user_id)
    if user is None:
        raise _http(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND", "成员不存在")

    if admin is not None and user.id == admin.id:
        raise _http(
            status.HTTP_400_BAD_REQUEST,
            "ADMIN_SELF_DELETE",
            "不能删除当前登录的管理员自己",
        )

    if user.role == "admin" and user.status == "active":
        remaining = await users.count_active_admins(exclude_id=user.id)
        if remaining < 1:
            raise _http(
                status.HTTP_400_BAD_REQUEST,
                "ADMIN_LOCKOUT",
                "不能删除最后一个 active 管理员，否则后台会被锁死",
            )

    await users.delete(user)
    return {"ok": True}


__all__ = ["router"]
