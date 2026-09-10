from __future__ import annotations

from pydantic import BaseModel


class ErrorPayload(BaseModel):
    code: str
    message: str
    retryable: bool = False


__all__ = ["ErrorPayload"]
