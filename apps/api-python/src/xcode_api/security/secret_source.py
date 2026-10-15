"""The ``SecretSource`` adapter: fresh codes and refresh tokens from the CSPRNG."""

from __future__ import annotations

from .codes import new_code
from .refresh_tokens import new_refresh_token


class RandomSecretSource:
    def verification_code(self) -> str:
        return new_code()

    def refresh_token(self) -> str:
        return new_refresh_token()
