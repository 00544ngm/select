from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes

from backend.security.provider_crypto import ProviderDecryptionError

CRYPTPROTECT_UI_FORBIDDEN = 0x01
APP_ENTROPY = b"bundling-console-v1"


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    blob = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


class WindowsDPAPI:
    prefix = "dpapi:"

    def encrypt(self, value: str) -> str:
        plain, plain_buffer = _blob(value.encode("utf-8"))
        entropy, entropy_buffer = _blob(APP_ENTROPY)
        output = DataBlob()
        _ = plain_buffer, entropy_buffer
        success = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(plain),
            None,
            ctypes.byref(entropy),
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output),
        )
        if not success:
            raise OSError(ctypes.get_last_error(), "DPAPI encryption failed")
        try:
            protected = ctypes.string_at(output.pbData, output.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(output.pbData)
        return self.prefix + base64.urlsafe_b64encode(protected).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value.startswith(self.prefix):
            raise ProviderDecryptionError("Provider credential must be migrated")
        try:
            protected_bytes = base64.urlsafe_b64decode(value[len(self.prefix) :])
            protected, protected_buffer = _blob(protected_bytes)
            entropy, entropy_buffer = _blob(APP_ENTROPY)
            output = DataBlob()
            _ = protected_buffer, entropy_buffer
            success = ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(protected),
                None,
                ctypes.byref(entropy),
                None,
                None,
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(output),
            )
            if not success:
                raise OSError(ctypes.get_last_error(), "DPAPI decryption failed")
            try:
                return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
            finally:
                ctypes.windll.kernel32.LocalFree(output.pbData)
        except (OSError, ValueError, UnicodeError) as error:
            raise ProviderDecryptionError(
                "Provider credential must be re-entered"
            ) from error

    @staticmethod
    def mask(value: str) -> str:
        return f"••••{value[-4:]}" if len(value) >= 4 else "••••"


__all__ = ["WindowsDPAPI"]
