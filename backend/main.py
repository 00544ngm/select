from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.router import router
from backend.config import BackendSettings, get_backend_settings
from backend.logging import RequestIDMiddleware, configure_logging

logger = logging.getLogger("backend")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    from app.core.config import settings as legacy_settings
    from backend.application.provider_clients import ProviderConnectionTester
    from backend.application.provider_service import ProviderService
    from backend.db.provider_repository import ProviderConfigurationRepository
    from backend.db.session import SessionFactory
    from backend.security.provider_crypto_factory import create_provider_crypto

    active_settings = get_backend_settings()
    if active_settings.runtime_mode == "desktop":
        from backend.application.job_recovery import recover_interrupted_jobs

        await recover_interrupted_jobs(SessionFactory)
    async with SessionFactory() as session:
        service = ProviderService(
            repository=ProviderConfigurationRepository(session),
            crypto=create_provider_crypto(active_settings),
            connection_test=ProviderConnectionTester(),
        )
        await service.import_legacy_env(legacy_settings)

    if active_settings.runtime_mode == "server":
        from backend.security.bootstrap import ensure_seed_admin

        await ensure_seed_admin(SessionFactory, active_settings)
    yield


def create_app(settings: BackendSettings | None = None) -> FastAPI:
    active_settings = settings or get_backend_settings()
    configure_logging()

    app = FastAPI(
        title="A+B Bundling API",
        version="0.1.15",
        docs_url="/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        # Server-mode control plane is a LAN web app: allow the configured
        # exact origins plus any loopback and private-network origin so
        # employees can open the console from their own machines on the LAN.
        # Credentials are Bearer tokens held in the operator's browser; the
        # data/API routes are login-gated, so opening CORS to private ranges
        # does not expose them to arbitrary web origins.
        allow_origin_regex=(
            r"^https?://(?:"
            r"localhost|127\.0\.0\.1|\[::1\]|"            # loopback
            r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"            # RFC1918 10/8
            r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"  # RFC1918 172.16/12
            r"192\.168\.\d{1,3}\.\d{1,3}|"               # RFC1918 192.168/16
            r"100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}"  # CGNAT 100.64/10
            r")(?::\d+)?$"
        ),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Request-ID",
            "X-Desktop-Session",
        ],
    )
    app.add_middleware(RequestIDMiddleware)
    if active_settings.runtime_mode == "desktop":
        from backend.security.desktop_session import DesktopSessionMiddleware

        app.add_middleware(
            DesktopSessionMiddleware,
            token=active_settings.desktop_session_token or "",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("Validation error", extra={"request_id": getattr(request.state, "request_id", "?")})
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "VALIDATION_ERROR",
                    "message": str(exc),
                    "retryable": False,
                }
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "?")
        logger.exception(
            "Unhandled exception",
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "retryable": True,
                }
            },
        )

    app.include_router(router, prefix=active_settings.api_prefix)
    return app


app = create_app()


__all__ = ["app", "create_app"]
