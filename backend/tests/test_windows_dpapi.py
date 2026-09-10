from __future__ import annotations

import pytest

from backend.security.provider_crypto import ProviderDecryptionError
from backend.security.windows_dpapi import WindowsDPAPI


def test_dpapi_ciphertext_does_not_contain_plaintext() -> None:
    store = WindowsDPAPI()

    encrypted = store.encrypt("sk-sensitive")

    assert "sk-sensitive" not in encrypted
    assert encrypted.startswith("dpapi:")
    assert store.decrypt(encrypted) == "sk-sensitive"


def test_dpapi_rejects_corrupted_ciphertext() -> None:
    with pytest.raises(ProviderDecryptionError):
        WindowsDPAPI().decrypt("dpapi:not-valid-base64")
