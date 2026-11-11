"""Six-digit verification codes and four-digit PINs from a CSPRNG, zero padded."""

from __future__ import annotations

import secrets

from ..domain.policies import PIN_LENGTH

CODE_DIGITS = 6


def new_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def new_pin() -> str:
    return f"{secrets.randbelow(10**PIN_LENGTH):0{PIN_LENGTH}d}"
