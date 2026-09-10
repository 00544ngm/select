from __future__ import annotations


class AppError(RuntimeError):
    def __init__(self, *, code: str, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class ServiceUnavailableError(AppError):
    pass


class NotFoundError(AppError):
    def __init__(self, *, message: str = "Resource was not found") -> None:
        super().__init__(code="NOT_FOUND", message=message, retryable=False)


class ConflictError(AppError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(code=code, message=message, retryable=False)


__all__ = ["AppError", "ConflictError", "NotFoundError", "ServiceUnavailableError"]
