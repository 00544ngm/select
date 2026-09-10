"""Admin editing of an ApiGroup's own multi-provider API settings.

Mirrors backend/api/routes/providers.py but operates on the provider rows owned
by one ApiGroup (GroupProviderRepository), NOT the global default set. Only
admins reach these endpoints (router-level require_admin); no loopback
restriction so group API settings can be maintained over the LAN.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import build_provider_service
from backend.api.routes.providers import _raise_provider_error
from backend.api.schemas.providers import (
    ProviderDraft,
    ProviderModelSelectionRequest,
    ProviderModelSelectionResult,
    ProviderModelVerifyRequest,
    ProviderModelVerifyResult,
    ProviderPublic,
    ProviderSlug,
    ProviderTestResult,
    ProviderUpdate,
)
from backend.application.provider_clients import ProviderConnectionError
from backend.application.provider_service import (
    ProviderConfigurationError,
    ProviderService,
)
from backend.db.auth_repository import ApiGroupRepository
from backend.db.provider_repository import GroupProviderRepository
from backend.db.session import get_session
from backend.security.auth import require_admin

router = APIRouter(
    prefix="/admin/api-groups/{group_id}/providers",
    tags=["admin-group-providers"],
    dependencies=[Depends(require_admin)],
)


async def get_group_provider_service(
    group_id: UUID = Path(...),
    session: AsyncSession = Depends(get_session),
) -> ProviderService:
    """Resolve a ProviderService bound to the requested ApiGroup's rows."""
    group = await ApiGroupRepository(session).get(group_id)
    if group is None or group.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "GROUP_NOT_FOUND",
                "message": "接口分组不存在或已停用",
                "retryable": False,
            },
        )
    return build_provider_service(
        GroupProviderRepository(session, api_group_id=group_id)
    )


@router.get("", response_model=list[ProviderPublic])
async def list_group_providers(
    group_id: UUID = Path(...),
    service: ProviderService = Depends(get_group_provider_service),
) -> list[ProviderPublic]:
    return await service.list_public()


@router.post("/{slug}/test", response_model=ProviderTestResult)
async def test_group_provider(
    group_id: UUID = Path(...),
    slug: ProviderSlug = Path(...),
    draft: ProviderDraft = ...,
    service: ProviderService = Depends(get_group_provider_service),
) -> ProviderTestResult:
    try:
        result = await service.test_draft(slug, draft)
    except (ProviderConfigurationError, ProviderConnectionError) as error:
        _raise_provider_error(error)
    return ProviderTestResult(message=result.message, models=list(result.models))


@router.put("/{slug}", response_model=ProviderPublic)
async def update_group_provider(
    group_id: UUID = Path(...),
    slug: ProviderSlug = Path(...),
    update: ProviderUpdate = ...,
    service: ProviderService = Depends(get_group_provider_service),
) -> ProviderPublic:
    try:
        return await service.save(slug, update)
    except (ProviderConfigurationError, ProviderConnectionError) as error:
        _raise_provider_error(error)
        raise AssertionError("unreachable")


@router.post("/{slug}/models/verify", response_model=ProviderModelVerifyResult)
async def verify_group_provider_model(
    group_id: UUID = Path(...),
    slug: ProviderSlug = Path(...),
    request: ProviderModelVerifyRequest = ...,
    service: ProviderService = Depends(get_group_provider_service),
) -> ProviderModelVerifyResult:
    try:
        return await service.verify_model(
            slug,
            request.model,
            set_default=request.set_default,
            is_automatic=request.is_automatic,
        )
    except (ProviderConfigurationError, ProviderConnectionError) as error:
        _raise_provider_error(error)
        raise AssertionError("unreachable")


@router.patch(
    "/{slug}/models/{model}/selection",
    response_model=ProviderModelSelectionResult,
)
async def select_group_provider_model(
    group_id: UUID = Path(...),
    slug: ProviderSlug = Path(...),
    model: str = Path(...),
    request: ProviderModelSelectionRequest = ...,
    service: ProviderService = Depends(get_group_provider_service),
) -> ProviderModelSelectionResult:
    try:
        return await service.set_model_selected(slug, model, request.is_selected)
    except (ProviderConfigurationError, ProviderConnectionError) as error:
        _raise_provider_error(error)
        raise AssertionError("unreachable")


__all__ = ["get_group_provider_service", "router"]
