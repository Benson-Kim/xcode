"""Trusted-device tokens (``docs/07-auth.md`` 12.1 and 12.8): 32 random bytes in Base64url
without padding (43 characters), returned to the device once; the database keeps only the
SHA-256 of the token's text, upper-case hex. The digest is unkeyed on purpose: a signing-key
rotation must not untrust every device, and 256 random bits need no key or salt."""

from __future__ import annotations

import base64
import hashlib
import secrets

TOKEN_BYTES = 32


def new_device_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(TOKEN_BYTES)).rstrip(b"=").decode("ascii")


def device_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest().upper()


class RandomDeviceTokens:
    """The ``DeviceTokens`` adapter."""

    def new(self) -> str:
        return new_device_token()

    def digest(self, token: str) -> str:
        return device_token_digest(token)
