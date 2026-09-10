from __future__ import annotations

from typing import Protocol


class CredentialStore(Protocol):
    def encrypt(self, value: str) -> str: ...

    def decrypt(self, value: str) -> str: ...


__all__ = ["CredentialStore"]
