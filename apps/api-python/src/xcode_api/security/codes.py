"""Six-digit verification codes from a CSPRNG, zero padded."""

from __future__ import annotations

import secrets

CODE_DIGITS = 6


def new_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
