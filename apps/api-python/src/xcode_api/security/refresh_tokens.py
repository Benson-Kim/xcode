"""Opaque refresh tokens: 48 random bytes in standard Base64 with padding (64 characters)."""

from __future__ import annotations

import base64
import secrets

TOKEN_BYTES = 48


def new_refresh_token() -> str:
    return base64.b64encode(secrets.token_bytes(TOKEN_BYTES)).decode("ascii")
