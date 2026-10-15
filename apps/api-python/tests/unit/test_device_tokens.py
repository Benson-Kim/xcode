"""Trusted-device tokens (``docs/07-auth.md`` 12.1): 32 random bytes as 43 Base64url characters,
stored only as the upper-case hex SHA-256 of their text, never the keyed digest."""

from __future__ import annotations

import base64
import hashlib

from xcode_api.domain.values import DeviceToken
from xcode_api.security.device_tokens import (
    RandomDeviceTokens,
    device_token_digest,
    new_device_token,
)
from xcode_api.security.digests import keyed_digest


def test_a_token_is_43_base64url_characters_of_32_random_bytes() -> None:
    tokens = {new_device_token() for _ in range(200)}
    assert len(tokens) == 200
    for token in tokens:
        assert len(token) == 43
        assert DeviceToken.valid(token)
        assert len(base64.urlsafe_b64decode(token + "=")) == 32


def test_the_digest_is_the_upper_hex_sha256_of_the_text() -> None:
    token = "abcDEF-_0123456789abcDEF-_0123456789abcDEF0"
    expected = hashlib.sha256(token.encode()).hexdigest().upper()
    assert device_token_digest(token) == expected
    assert len(expected) == 64
    assert device_token_digest(token) != keyed_digest(token, "a-signing-key-of-at-least-32-bytes!!")


def test_the_adapter_uses_both() -> None:
    adapter = RandomDeviceTokens()
    token = adapter.new()
    assert len(token) == 43
    assert adapter.digest(token) == device_token_digest(token)
