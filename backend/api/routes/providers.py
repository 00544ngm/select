from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.api.dependencies import get_provider_service
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
from backend.security.auth import require_admin


def require_loopback(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "test"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "SETTINGS_LOCAL_ONLY",
                "message": "API settings are available only on this computer",
                "retryable": False,
            },
        )


router = APIRouter(
    prefix="/settings/providers",
    tags=["provider-settings"],
    dependencies=[Depends(require_loopback), Depends(require_admin)],
)


def _raise_provider_error(error: Exception) -> None:
    if isinstance(error, (ProviderConfigurationError, ProviderConnectionError)):
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
                if error.retryable
                else status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail={
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        ) from error
    raise error


@router.get("", response_model=list[ProviderPublic])
async def list_providers(
    service: ProviderService = Depends(get_provider_service),
) -> list[ProviderPublic]:
    return await service.list_public()


@router.post("/{slug}/test", response_model=ProviderTestResult)
async def test_provider(
    slug: ProviderSlug,
    draft: ProviderDraft,
    service: ProviderService = Depends(get_provider_service),
) -> ProviderTestResult:
    try:
        result = await service.test_draft(slug, draft)
    except (ProviderConfigurationError, ProviderConnectionError) as error:
        _raise_provider_error(error)
    return ProviderTestResult(message=result.message, models=list(result.models))


@router.put("/{slug}", response_model=ProviderPublic)
async def update_provider(
    slug: ProviderSlug,
    update: ProviderUpdate,
    service: ProviderService = Depends(get_provider_service),
) -> ProviderPublic:
    try:
        return await service.save(slug, update)
    except (ProviderConfigurationError, ProviderConnectionError) as error:
        _raise_provider_error(error)
        raise AssertionError("unreachable")


@router.post("/{slug}/models/verify", response_model=ProviderModelVerifyResult)
async def verify_provider_model(
    slug: ProviderSlug,
    request: ProviderModelVerifyRequest,
    service: ProviderService = Depends(get_provider_service),
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
async def select_provider_model(
    slug: ProviderSlug,
    model: str,
    request: ProviderModelSelectionRequest,
    service: ProviderService = Depends(get_provider_service),
) -> ProviderModelSelectionResult:
    try:
        return await service.set_model_selected(slug, model, request.is_selected)
    except (ProviderConfigurationError, ProviderConnectionError) as error:
        _raise_provider_error(error)
        raise AssertionError("unreachable")


__all__ = ["require_loopback", "router"]
