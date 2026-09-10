from fastapi import APIRouter

from backend.desktop.diagnostics import run_desktop_diagnostics

router = APIRouter(prefix="/desktop", tags=["desktop"])


@router.get("/diagnostics")
async def desktop_diagnostics():
    return await run_desktop_diagnostics()


__all__ = ["router"]
