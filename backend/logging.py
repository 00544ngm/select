from __future__ import annotations

import logging
import uuid

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class RequestIDFilter(logging.Filter):
    """Keep request-id logging safe for records created outside HTTP requests."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(request_id)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if not any(isinstance(item, RequestIDFilter) for item in handler.filters):
            handler.addFilter(RequestIDFilter())


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
        request.state.request_id = request_id

        logger = logging.getLogger("backend")
        extra = {"request_id": request_id}
        logger.debug("Request started", extra=extra)

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


__all__ = ["RequestIDFilter", "RequestIDMiddleware", "configure_logging"]
