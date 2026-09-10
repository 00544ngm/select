from fastapi import APIRouter

from backend.api.routes.admin import router as admin_router
from backend.api.routes.auth import router as auth_router
from backend.api.routes.group_providers import router as group_providers_router
from backend.api.routes.health import router as health_router
from backend.api.routes.diagnostics import router as diagnostics_router
from backend.api.routes.jobs import router as jobs_router
from backend.api.routes.providers import router as providers_router
from backend.api.routes.search import router as search_router
from backend.api.routes.workbench import router as workbench_router


router = APIRouter()
router.include_router(diagnostics_router)
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(admin_router)
router.include_router(group_providers_router)
router.include_router(jobs_router)
router.include_router(search_router)
router.include_router(workbench_router)
router.include_router(providers_router)


__all__ = ["router"]
