"""Value objects with their normalisation rules, and the write result every command returns.

These are the only rules the API tier applies to shape and normalise input before the
database decides; the routines check the same bounds again. Secret values (PINs, codes,
refresh tokens) and personal data (phone numbers) never appear in a ``repr``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import IntEnum, StrEnum
from uuid import UUID

from .policies import PIN_CEILING

MAX_PAGE = 100_000
MAX_PAGE_SIZE = 100
MONEY_CAP = Decimal("999999999999.99")

_TWO_PLACES = Decimal("0.01")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class Money:
    """A positive amount with at most two decimal places, below 10^12 (``numeric(14,2)``).

    Normalised to exactly two places; more places are refused, never rounded.
    """

    amount: Decimal

    def __init__(self, value: Decimal | int | str) -> None:
        if isinstance(value, bool) or not isinstance(value, Decimal | int | str):
            raise ValueError(f"not a valid money amount: {value!r}")
        try:
            parsed = Decimal(value.strip() if isinstance(value, str) else value)
        except InvalidOperation as exc:
            raise ValueError(f"not a valid money amount: {value!r}") from exc
        if not parsed.is_finite():
            raise ValueError("money amount must be a finite number")
        if parsed <= 0:
            raise ValueError("money amount must be positive")
        if parsed > MONEY_CAP:
            raise ValueError("money amount must be below 1 000 000 000 000")
        quantised = parsed.quantize(_TWO_PLACES)
        if parsed != quantised:
            raise ValueError("money amount has more than two decimal places")
        object.__setattr__(self, "amount", quantised)


@dataclass(frozen=True, slots=True)
class Version:
    """A row concurrency token. Users and refresh tokens start at 0, other rows at 1."""

    value: int

    def __post_init__(self) -> None:
        if not _is_int(self.value):
            raise ValueError("version must be an integer")
        if self.value < 0:
            raise ValueError("version must not be negative")


@dataclass(frozen=True, slots=True)
class PageRequest:
    """``page`` 1 to 100 000 and ``page_size`` 1 to 100; out-of-range values are refused,
    never clamped."""

    page: int = 1
    page_size: int = 25

    def __post_init__(self) -> None:
        if not _is_int(self.page) or not 1 <= self.page <= MAX_PAGE:
            raise ValueError(f"page must be 1 to {MAX_PAGE}")
        if not _is_int(self.page_size) or not 1 <= self.page_size <= MAX_PAGE_SIZE:
            raise ValueError(f"page size must be 1 to {MAX_PAGE_SIZE}")


@dataclass(frozen=True, slots=True)
class DeviceId:
    """An opaque client-chosen device identifier: 1 to 128 code points, no meaning assigned.

    U+0000 is refused because PostgreSQL text cannot hold it.
    """

    MAX_LENGTH = 128

    value: str

    def __post_init__(self) -> None:
        value = self.value
        if not 1 <= len(value) <= self.MAX_LENGTH:
            raise ValueError("device id must be 1 to 128 characters")
        if "\x00" in value:
            raise ValueError("device id must not contain U+0000")


_EMAIL_FORBIDDEN = re.compile(r'[\s<>()\[\],;:\\"@]')


@dataclass(frozen=True, slots=True)
class Email:
    """An email address as ``local@domain`` only (display-name forms are refused): trimmed,
    lower-cased, at most 320 characters."""

    MAX_LENGTH = 320

    value: str

    def __init__(self, value: str) -> None:
        normalised = value.strip().lower()
        if len(normalised) > self.MAX_LENGTH:
            raise ValueError("email must be at most 320 characters")
        local, at, domain = normalised.partition("@")
        if not at or not local or not domain:
            raise ValueError("email must be local@domain")
        if _EMAIL_FORBIDDEN.search(local) or _EMAIL_FORBIDDEN.search(domain):
            raise ValueError("email must be local@domain without spaces or quoting")
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in normalised):
            raise ValueError("email must not contain control characters")
        if domain.startswith(".") or domain.endswith(".") or ".." in domain:
            raise ValueError("email domain is malformed")
        object.__setattr__(self, "value", normalised)

    @classmethod
    def parse(cls, value: str) -> Email | None:
        try:
            return cls(value)
        except ValueError:
            return None


_KENYAN_MOBILE = (
    (re.compile(r"254[17][0-9]{8}"), 3),
    (re.compile(r"0[17][0-9]{8}"), 1),
    (re.compile(r"[17][0-9]{8}"), 0),
)


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    """A Kenyan mobile number normalised to ``+254XXXXXXXXX``.

    The twin of ``identity.normalize_phone`` (parity-tested): every character that is not a
    decimal digit is stripped, as in .NET; a decimal digit outside 0-9 makes the input "not a
    number"; and the 12-, 10- and 9-digit forms with a subscriber part ``[17][0-9]{8}``
    normalise.
    """

    MAX_INPUT_LENGTH = 14

    value: str = field(repr=False)

    @classmethod
    def parse(cls, text: str) -> PhoneNumber | None:
        if any(ch.isdecimal() and not "0" <= ch <= "9" for ch in text):
            return None
        digits = "".join(ch for ch in text if "0" <= ch <= "9")
        for pattern, prefix in _KENYAN_MOBILE:
            if pattern.fullmatch(digits):
                return cls("+254" + digits[prefix:])
        return None


class Pin:
    """The bound of a PIN as a request carries it: at most 8 characters, so a PIN of five to
    eight digits set before the four-digit rule still verifies. A new PIN's rules are
    ``domain/policies.py`` ``new_pin_problem``."""

    MAX_LENGTH = PIN_CEILING


_DEVICE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .()+-]{0,59}")
_DEVICE_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,64}")


class DeviceName:
    """The name a device gives itself on the new sign-in routes: trimmed, 1 to 60 characters
    of letters, digits, space and ``.()+-``, starting with a letter or digit; an absent or empty
    name is unknown (``None``). The narrow alphabet keeps links and addresses out of the code
    email a stranger can trigger (``docs/07-auth.md`` 12.1)."""

    MAX_LENGTH = 60

    @staticmethod
    def parse(text: str) -> str | None:
        """The trimmed name, ``None`` for an empty one; ``ValueError`` when it breaks the rule."""
        value = text.strip(" ")
        if value == "":
            return None
        if _DEVICE_NAME.fullmatch(value) is None:
            raise ValueError("a device name is 1 to 60 letters, digits, spaces or .()+-")
        return value


class DeviceToken:
    """A trusted-device token as a device presents it: 1 to 64 Base64url characters."""

    MAX_LENGTH = 64

    @staticmethod
    def valid(text: str) -> bool:
        return _DEVICE_TOKEN.fullmatch(text) is not None


@dataclass(frozen=True, slots=True)
class VerificationCode:
    """A verification code as typed by a person: at most 32 characters."""

    MAX_LENGTH = 32

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.value) > self.MAX_LENGTH:
            raise ValueError("a code must be at most 32 characters")


@dataclass(frozen=True, slots=True)
class RefreshToken:
    """An opaque refresh token as presented by a client: at most 256 characters."""

    MAX_LENGTH = 256

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.value) > self.MAX_LENGTH:
            raise ValueError("a refresh token must be at most 256 characters")


class CodedEnum(IntEnum):
    """An enumeration stored as a code-table integer; members carry the label clients show."""

    @property
    def label(self) -> str:
        raise NotImplementedError


class WriteOutcome(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    REPLAYED = "replayed"


@dataclass(frozen=True, slots=True)
class WriteResult:
    """``api.write_result``: the row a command wrote, its version after the write, and how."""

    id: UUID
    version: int
    outcome: WriteOutcome
