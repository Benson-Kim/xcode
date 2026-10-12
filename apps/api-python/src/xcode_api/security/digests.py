"""Keyed digests of verification codes and refresh tokens (``docs/07-auth.md`` section 1):
HMAC-SHA256 over the UTF-8 value with the signing key, upper-case hex. Only digests are
stored, so the database never holds a usable code or token."""

from __future__ import annotations

import hashlib
import hmac


def keyed_digest(value: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest().upper()


class KeyedDigester:
    """The ``CodeHasher`` adapter: ``keyed_digest`` with the current signing key."""

    __slots__ = ("_key",)

    def __init__(self, key: str) -> None:
        self._key = key

    def digest(self, value: str) -> str:
        return keyed_digest(value, self._key)
