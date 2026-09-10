from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class ProviderDecryptionError(RuntimeError):
    """Raised when stored provider credentials cannot be decrypted."""


class ProviderCrypto:
    def __init__(self, *, key_file: Path, configured_key: str | None = None) -> None:
        self._key_file = key_file
        key = configured_key.encode("ascii") if configured_key else self._load_or_create_key()
        self._fernet = Fernet(key)

    def _load_or_create_key(self) -> bytes:
        if self._key_file.exists():
            return self._key_file.read_bytes().strip()

        self._key_file.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        self._key_file.write_bytes(key + b"\n")
        try:
            os.chmod(self._key_file, 0o600)
        except OSError:
            pass
        return key

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as error:
            raise ProviderDecryptionError(
                "Provider credential must be re-entered"
            ) from error

    @staticmethod
    def mask(value: str) -> str:
        return f"••••{value[-4:]}" if len(value) >= 4 else "••••"


__all__ = ["ProviderCrypto", "ProviderDecryptionError"]
