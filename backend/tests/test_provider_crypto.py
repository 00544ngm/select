from __future__ import annotations

import pytest

from backend.security.provider_crypto import ProviderCrypto, ProviderDecryptionError


def test_crypto_round_trip_and_mask(tmp_path):
    key_file = tmp_path / "provider.key"
    crypto = ProviderCrypto(key_file=key_file)

    encrypted = crypto.encrypt("sk-test-secret-4F2A")

    assert encrypted != "sk-test-secret-4F2A"
    assert crypto.decrypt(encrypted) == "sk-test-secret-4F2A"
    assert crypto.mask("sk-test-secret-4F2A") == "••••4F2A"
    assert key_file.exists()


def test_short_key_has_no_identifying_suffix(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")

    assert crypto.mask("abc") == "••••"


def test_wrong_key_raises_stable_decryption_error(tmp_path):
    first = ProviderCrypto(key_file=tmp_path / "first.key")
    second = ProviderCrypto(key_file=tmp_path / "second.key")

    with pytest.raises(ProviderDecryptionError, match="re-entered"):
        second.decrypt(first.encrypt("sk-secret"))

