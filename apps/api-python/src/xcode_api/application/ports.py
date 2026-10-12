"""Ports a use case depends on. Each Protocol's docstring is its contract."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from ..domain.identity import AccessGrant, CodePurpose, TokenClaims


@dataclass(frozen=True, slots=True)
class MailMessage:
    """One email to send: recipient address, subject and plain-text body, plus non-secret
    ``tags`` for the delivery log lines. Neither the address nor the body is in ``repr``."""

    to: str = field(repr=False)
    subject: str
    text: str = field(repr=False)
    tags: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VerificationMail:
    """A verification code for the stored address of an account. The delivery log names
    the purpose, the code id and the request id, never the code or the address."""

    to: str = field(repr=False)
    purpose: CodePurpose
    code: str = field(repr=False)
    code_id: UUID
    request_id: str
    device_name: str | None = None


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """The outcome of charging one hit against a fixed window.

    ``allowed`` is false when the window is already full; ``remaining`` is how many hits
    are still allowed in the current window (0 when refused); ``retry_after_seconds`` is
    the whole number of seconds until the current window ends.
    """

    allowed: bool
    remaining: int
    retry_after_seconds: int


@runtime_checkable
class Clock(Protocol):
    """Source of the current time. ``now()`` returns a timezone-aware UTC ``datetime``."""

    def now(self) -> datetime: ...


@runtime_checkable
class TokenIssuer(Protocol):
    """Issues and verifies access tokens.

    ``issue`` signs a grant with the current key, valid from ``now`` for the grant's
    lifetime. ``verify`` validates the algorithm, signature (current key, then the previous
    keys), issuer, audience and lifetime at ``now`` with zero leeway and returns the claims;
    any failure raises ``SessionInvalid``. Adapter: ``security/tokens.py``.
    """

    def issue(self, grant: AccessGrant, *, now: datetime) -> str: ...

    def verify(self, token: str, *, now: datetime) -> TokenClaims: ...


@runtime_checkable
class PinHasher(Protocol):
    """Hashes and verifies PINs.

    ``hash`` derives a stored representation; ``verify`` compares in constant time.
    ``dummy_verify`` runs one derivation against a fixed dummy hash so that an unknown
    account costs the same as a known one. CPU-bound work runs off the event loop on a
    bounded pool; each method raises ``TransientFailure`` instead of waiting when the pool
    and its queue are full, before any decision is taken. Adapter: ``security/pins.py``.
    """

    async def hash(self, pin: str) -> str: ...

    async def verify(self, pin: str, stored: str) -> bool: ...

    async def dummy_verify(self, pin: str) -> bool: ...


@runtime_checkable
class CodeHasher(Protocol):
    """Produces the stored digest of a verification code or refresh token.

    Deterministic keyed digest (HMAC-SHA256, uppercase hex); never reversible. Adapter:
    ``security/digests.py``.
    """

    def digest(self, value: str) -> str: ...


@runtime_checkable
class SecretSource(Protocol):
    """Fresh secrets from a CSPRNG: a six-digit, zero-padded verification code and an opaque
    refresh token (48 random bytes, Base64). Adapter: ``security/secret_source.py``."""

    def verification_code(self) -> str: ...

    def refresh_token(self) -> str: ...


@runtime_checkable
class DeviceTokens(Protocol):
    """Trusted-device tokens: ``new`` returns 32 random bytes as 43 Base64url characters,
    returned to the device once; ``digest`` is the SHA-256 of the token's text in upper-case
    hex, the only form stored. Adapter: ``security/device_tokens.py``."""

    def new(self) -> str: ...

    def digest(self, token: str) -> str: ...


@runtime_checkable
class CodeMailer(Protocol):
    """Delivers verification codes. Adapter: ``infra/mail.py`` ``VerificationMailer``.

    ``send_now`` delivers before it returns, within the mail timeout, and answers whether
    the message was sent; a failure is logged, never raised. ``send_later`` queues the
    message for delivery after the reply; when that delivery fails, ``on_failure`` runs
    (its own failure is logged and swallowed).
    """

    async def send_now(self, mail: VerificationMail) -> bool: ...

    def send_later(
        self, mail: VerificationMail, *, on_failure: Callable[[], Awaitable[None]]
    ) -> None: ...


@runtime_checkable
class Mailer(Protocol):
    """Sends one message.

    Raises ``MailDeliveryError`` on failure; the caller decides whether to withdraw the
    code. Never raises to leak whether a recipient exists.
    """

    async def send(self, message: MailMessage) -> None: ...


@runtime_checkable
class RateLimiter(Protocol):
    """Charges one hit against a fixed window keyed by ``key``.

    Returns a :class:`RateLimitDecision`. Never raises for an ordinary refusal; a backend
    outage raises and the caller maps it to a transient failure.
    """

    async def hit(
        self, key: str, limit: int, window_seconds: int, now: datetime
    ) -> RateLimitDecision: ...
