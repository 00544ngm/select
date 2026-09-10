"""Read-only 'what can I use' surface for the logged-in operator.

An employee only ever sees the provider catalog of the ApiGroup they are
assigned to (masked keys, no editing). An admin or an ungrouped employee sees
the global default set. This is the sole source for the task model picker so an
employee can never pick a provider/model outside their group.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import build_provider_service
from backend.api.schemas.providers import ProviderPublic
from backend.db.models import User
from backend.db.provider_repository import GroupProviderRepository
from backend.db.session import get_session
from backend.security.auth import get_current_user

router = APIRouter(
    prefix="/workbench",
    tags=["workbench"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/providers", response_model=list[ProviderPublic])
async def my_providers(
    user: User | None = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderPublic]:
    if user is not None and user.api_group_id is not None:
        repository = GroupProviderRepository(
            session, api_group_id=user.api_group_id
        )
    else:
        from backend.db.provider_repository import ProviderConfigurationRepository

        repository = ProviderConfigurationRepository(session)
    return await build_provider_service(repository).list_public()


__all__ = ["router"]
