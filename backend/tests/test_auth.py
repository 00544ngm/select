from __future__ import annotations

from backend.security.auth import (
    decode_token,
    hash_password,
    sign_token,
    verify_password,
)


def test_hash_and_verify_password_roundtrip():
    digest, salt = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", digest, salt)
    assert not verify_password("wrong password", digest, salt)


def test_hash_password_with_existing_salt_is_deterministic():
    digest1, salt = hash_password("secret123")
    digest2, _ = hash_password("secret123", salt)
    assert digest1 == digest2


def test_sign_and_decode_token_roundtrip():
    token = sign_token(sub="abc", username="admin", secret="s3cret", ttl_seconds=3600)
    payload = decode_token(token, "s3cret")
    assert payload is not None
    assert payload["sub"] == "abc"
    assert payload["username"] == "admin"


def test_decode_token_rejects_wrong_secret():
    token = sign_token(sub="abc", username="admin", secret="s3cret", ttl_seconds=3600)
    assert decode_token(token, "other") is None


def test_decode_token_rejects_garbage():
    assert decode_token("not-a-token", "s3cret") is None
