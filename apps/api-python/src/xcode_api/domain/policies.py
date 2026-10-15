"""The pure rules the API tier applies itself because the database cannot.

The rules of a new PIN before hashing, the one uniform refusal every released sign-in failure
gets, when the dummy hash must be verified instead of a stored one, and how a routine's
outcome becomes the wire envelope (``docs/07-auth.md``, ``docs/06-http-contract.md`` sections
1.6 A and 2.12.1).
"""

from __future__ import annotations

from types import MappingProxyType

from .identity import (
    AccountState,
    AuthEnvelope,
    AuthOutcome,
    AuthOutcomeKind,
    EnvelopeStatus,
    PinProblem,
    UserStatus,
)

PIN_LENGTH = 4
PIN_CEILING = 8
PIN_TRIES = 5
CODE_TRIES = 3
TRUSTED_DEVICE_IDLE_DAYS = 90

_RUNS = ("0123456789", "9876543210")

_REFUSAL = AuthEnvelope(EnvelopeStatus.AUTHENTICATION_FAILED)
_INVALID_REQUEST = AuthEnvelope(EnvelopeStatus.INVALID_REQUEST)
_SERVICE_UNAVAILABLE = AuthEnvelope(EnvelopeStatus.SERVICE_UNAVAILABLE)
_INVALID_PIN = AuthEnvelope(EnvelopeStatus.INVALID_PIN, minimum_pin_length=PIN_LENGTH)

_PLAIN = MappingProxyType(
    {
        AuthOutcomeKind.AUTHENTICATED: AuthEnvelope(EnvelopeStatus.AUTHENTICATED),
        AuthOutcomeKind.CHECK_EMAIL: AuthEnvelope(EnvelopeStatus.CHECK_EMAIL),
        AuthOutcomeKind.SILENT: AuthEnvelope(EnvelopeStatus.CHECK_EMAIL),
        AuthOutcomeKind.CODE_VERIFIED: AuthEnvelope(EnvelopeStatus.CODE_VERIFIED),
        AuthOutcomeKind.REFUSED: _REFUSAL,
        AuthOutcomeKind.SIGNED_OUT: AuthEnvelope(EnvelopeStatus.SIGNED_OUT),
        AuthOutcomeKind.DEVICE_REVOKED: AuthEnvelope(EnvelopeStatus.DEVICE_REVOKED),
        AuthOutcomeKind.PIN_REQUIRED: _REFUSAL,
        AuthOutcomeKind.PIN_LOCKED: _REFUSAL,
        AuthOutcomeKind.BLOCKED: _REFUSAL,
        AuthOutcomeKind.CODE_RESENT: _REFUSAL,
        AuthOutcomeKind.PIN_CHANGED: _REFUSAL,
    }
)

_STEP = MappingProxyType(
    {
        AuthOutcomeKind.AUTHENTICATED: EnvelopeStatus.AUTHENTICATED,
        AuthOutcomeKind.VERIFICATION_REQUIRED: EnvelopeStatus.VERIFICATION_REQUIRED,
        AuthOutcomeKind.CHECK_EMAIL: EnvelopeStatus.VERIFICATION_REQUIRED,
        AuthOutcomeKind.SILENT: EnvelopeStatus.VERIFICATION_REQUIRED,
        AuthOutcomeKind.CODE_VERIFIED: EnvelopeStatus.CODE_VERIFIED,
        AuthOutcomeKind.INVALID_PIN: EnvelopeStatus.INVALID_PIN,
        AuthOutcomeKind.REFUSED: EnvelopeStatus.AUTHENTICATION_FAILED,
        AuthOutcomeKind.DEVICE_REVOKED: EnvelopeStatus.DEVICE_REVOKED,
        AuthOutcomeKind.PIN_REQUIRED: EnvelopeStatus.PIN_REQUIRED,
        AuthOutcomeKind.PIN_LOCKED: EnvelopeStatus.PIN_LOCKED,
        AuthOutcomeKind.BLOCKED: EnvelopeStatus.BLOCKED,
        AuthOutcomeKind.CODE_RESENT: EnvelopeStatus.CODE_RESENT,
        AuthOutcomeKind.PIN_CHANGED: EnvelopeStatus.PIN_CHANGED,
    }
)


def new_pin_problem(pin: str, phone: str | None, replaced: str | None = None) -> PinProblem | None:
    """The first rule a new PIN breaks, or ``None``: exactly four ASCII digits (``length``);
    not one digit four times, not four consecutive digits up or down, not the last four
    digits of the person's own number (``weak``); not the PIN being replaced (``unchanged``).
    ``phone`` is the person's number in any form (only its digits count)."""
    if len(pin) != PIN_LENGTH or not all("0" <= ch <= "9" for ch in pin):
        return PinProblem.LENGTH
    if len(set(pin)) == 1 or any(pin in run for run in _RUNS):
        return PinProblem.WEAK
    digits = "".join(ch for ch in phone or "" if "0" <= ch <= "9")
    if len(digits) >= PIN_LENGTH and pin == digits[-PIN_LENGTH:]:
        return PinProblem.WEAK
    if replaced is not None and pin == replaced:
        return PinProblem.UNCHANGED
    return None


def refusal_answer() -> AuthEnvelope:
    """The single answer for every refusal on the released routes: unknown number, removed
    account, wrong PIN, a lock or a forced reset seen from an untrusted device, bad code or
    token. Always the same object."""
    return _REFUSAL


def invalid_request_answer() -> AuthEnvelope:
    return _INVALID_REQUEST


def service_unavailable_answer() -> AuthEnvelope:
    return _SERVICE_UNAVAILABLE


def invalid_pin_answer() -> AuthEnvelope:
    """A new PIN refused on a released route: every problem answers the floor of four and
    nothing else (the v2.11 envelope has no ``pinProblem``)."""
    return _INVALID_PIN


def invalid_pin_step(problem: PinProblem) -> AuthEnvelope:
    """A new PIN refused on a route of the number-first flow."""
    return AuthEnvelope(
        EnvelopeStatus.INVALID_PIN, minimum_pin_length=PIN_LENGTH, pin_problem=problem
    )


def needs_dummy_hash(state: AccountState | None) -> bool:
    """True when no stored hash may be verified (unknown or removed account, no PIN, a forced
    reset pending), so the dummy hash is verified instead and every PIN check costs one
    derivation."""
    return (
        state is None
        or state.status is not UserStatus.ACTIVE
        or state.pin_hash is None
        or state.pin_reset_required
    )


def envelope_for(outcome: AuthOutcome) -> AuthEnvelope:
    """The released routes' envelope of an outcome. Tokens and the development code are not
    outcome fields; the use case adds them."""
    kind = outcome.outcome
    if kind is AuthOutcomeKind.VERIFICATION_REQUIRED:
        return AuthEnvelope(EnvelopeStatus.VERIFICATION_REQUIRED, masked_email=outcome.masked_email)
    if kind is AuthOutcomeKind.PAUSED:
        return AuthEnvelope(EnvelopeStatus.PAUSED, retry_after_seconds=outcome.retry_after_seconds)
    if kind is AuthOutcomeKind.INVALID_PIN:
        return _INVALID_PIN
    return _PLAIN[kind]


def step_envelope_for(outcome: AuthOutcome, *, masked: bool = True) -> AuthEnvelope:
    """The number-first routes' envelope of an outcome: the status, the code's purpose, the
    tries left of a refused PIN or code, the problem of a refused new PIN, and the masked
    address unless ``masked`` is false (the answers that must not tell an unknown number
    apart: "Forgot PIN" and "Send a new code")."""
    status = _STEP[outcome.outcome]
    return AuthEnvelope(
        status,
        masked_email=outcome.masked_email
        if masked and status is EnvelopeStatus.VERIFICATION_REQUIRED
        else None,
        minimum_pin_length=PIN_LENGTH if status is EnvelopeStatus.INVALID_PIN else None,
        purpose=outcome.purpose
        if status in (EnvelopeStatus.VERIFICATION_REQUIRED, EnvelopeStatus.CODE_RESENT)
        else None,
        tries_left=outcome.tries_left if status is EnvelopeStatus.AUTHENTICATION_FAILED else None,
        pin_problem=outcome.pin_problem if status is EnvelopeStatus.INVALID_PIN else None,
    )
