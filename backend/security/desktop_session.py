from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class DesktopSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method == "OPTIONS" or request.url.path.endswith("/health/live"):
            return await call_next(request)
        supplied = request.headers.get("X-Desktop-Session", "")
        if not self._token or not secrets.compare_digest(supplied, self._token):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "code": "DESKTOP_SESSION_REQUIRED",
                        "message": "桌面会话已失效，请重新打开软件",
                        "retryable": False,
                    }
                },
            )
        return await call_next(request)


__all__ = ["DesktopSessionMiddleware"]
