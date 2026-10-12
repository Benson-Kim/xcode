"""The pure auth rules of ``domain/policies.py``: the new-PIN rules, the one refusal answer of
the released routes, the dummy-hash rule and the outcome-to-envelope maps of both envelopes."""

from __future__ import annotations

from uuid import uuid4

import pytest

from xcode_api.domain.identity import (
    AccountState,
    AuthEnvelope,
    AuthOutcome,
    AuthOutcomeKind,
    CodePurpose,
    EnvelopeStatus,
    PinProblem,
    SignInRefusal,
    UserStatus,
)
from xcode_api.domain.policies import (
    CODE_TRIES,
    PIN_CEILING,
    PIN_LENGTH,
    PIN_TRIES,
    TRUSTED_DEVICE_IDLE_DAYS,
    envelope_for,
    invalid_pin_answer,
    invalid_pin_step,
    needs_dummy_hash,
    new_pin_problem,
    refusal_answer,
    step_envelope_for,
)

FULLWIDTH_FIVE = chr(0xFF15)
OWN_NUMBER = "0712349051"


@pytest.mark.parametrize(
    ("pin", "replaced", "problem"),
    [
        ("123", None, PinProblem.LENGTH),
        ("", None, PinProblem.LENGTH),
        ("12345", None, PinProblem.LENGTH),
        ("90817263", None, PinProblem.LENGTH),
        ("58a6", None, PinProblem.LENGTH),
        ("58 6", None, PinProblem.LENGTH),
        ("5" + FULLWIDTH_FIVE + "26", None, PinProblem.LENGTH),
        ("1111", None, PinProblem.WEAK),
        ("0000", None, PinProblem.WEAK),
        ("1234", None, PinProblem.WEAK),
        ("0123", None, PinProblem.WEAK),
        ("6789", None, PinProblem.WEAK),
        ("4321", None, PinProblem.WEAK),
        ("9876", None, PinProblem.WEAK),
        ("3210", None, PinProblem.WEAK),
        ("9051", None, PinProblem.WEAK),
        ("5826", "5826", PinProblem.UNCHANGED),
        ("1111", "1111", PinProblem.WEAK),
        ("8901", None, None),
        ("7890", None, None),
        ("2468", None, None),
        ("1123", None, None),
        ("5826", "3971", None),
    ],
)
def test_new_pin_problems(pin: str, replaced: str | None, problem: PinProblem | None) -> None:
    assert new_pin_problem(pin, OWN_NUMBER, replaced) is problem


@pytest.mark.parametrize("phone", ["+254712349051", "254712349051", "712349051", "0712 349 051"])
def test_the_last_four_digits_of_the_number_in_any_form_are_weak(phone: str) -> None:
    assert new_pin_problem("9051", phone) is PinProblem.WEAK


def test_without_a_number_only_the_other_rules_apply() -> None:
    assert new_pin_problem("9051", None) is None
    assert new_pin_problem("9051", "") is None


def test_constants() -> None:
    assert (PIN_LENGTH, PIN_CEILING, PIN_TRIES, CODE_TRIES, TRUSTED_DEVICE_IDLE_DAYS) == (
        4,
        8,
        5,
        3,
        90,
    )


@pytest.mark.parametrize("refusal", [None, *SignInRefusal])
def test_every_refusal_gets_the_one_refusal_object(refusal: SignInRefusal | None) -> None:
    outcome = AuthOutcome(AuthOutcomeKind.REFUSED, refusal=refusal, tries_left=3)
    assert envelope_for(outcome) is refusal_answer()
    assert refusal_answer() is refusal_answer()
    assert refusal_answer() == AuthEnvelope(EnvelopeStatus.AUTHENTICATION_FAILED)


_EXPECTED = {
    AuthOutcomeKind.AUTHENTICATED: AuthEnvelope(EnvelopeStatus.AUTHENTICATED),
    AuthOutcomeKind.VERIFICATION_REQUIRED: AuthEnvelope(
        EnvelopeStatus.VERIFICATION_REQUIRED, masked_email="j***@example.com"
    ),
    AuthOutcomeKind.CHECK_EMAIL: AuthEnvelope(EnvelopeStatus.CHECK_EMAIL),
    AuthOutcomeKind.SILENT: AuthEnvelope(EnvelopeStatus.CHECK_EMAIL),
    AuthOutcomeKind.CODE_VERIFIED: AuthEnvelope(EnvelopeStatus.CODE_VERIFIED),
    AuthOutcomeKind.INVALID_PIN: AuthEnvelope(EnvelopeStatus.INVALID_PIN, minimum_pin_length=4),
    AuthOutcomeKind.PAUSED: AuthEnvelope(EnvelopeStatus.PAUSED, retry_after_seconds=900),
    AuthOutcomeKind.REFUSED: AuthEnvelope(EnvelopeStatus.AUTHENTICATION_FAILED),
    AuthOutcomeKind.SIGNED_OUT: AuthEnvelope(EnvelopeStatus.SIGNED_OUT),
    AuthOutcomeKind.DEVICE_REVOKED: AuthEnvelope(EnvelopeStatus.DEVICE_REVOKED),
    # The outcomes of the number-first routes never reach a released route; if one did, the
    # released client gets the one refusal it knows.
    AuthOutcomeKind.PIN_REQUIRED: AuthEnvelope(EnvelopeStatus.AUTHENTICATION_FAILED),
    AuthOutcomeKind.PIN_LOCKED: AuthEnvelope(EnvelopeStatus.AUTHENTICATION_FAILED),
    AuthOutcomeKind.BLOCKED: AuthEnvelope(EnvelopeStatus.AUTHENTICATION_FAILED),
    AuthOutcomeKind.CODE_RESENT: AuthEnvelope(EnvelopeStatus.AUTHENTICATION_FAILED),
    AuthOutcomeKind.PIN_CHANGED: AuthEnvelope(EnvelopeStatus.AUTHENTICATION_FAILED),
}


def _outcome(kind: AuthOutcomeKind) -> AuthOutcome:
    return AuthOutcome(
        kind,
        retry_after_seconds=900,
        masked_email="j***@example.com",
        minimum_pin_length=6,
        email="jane.doe@example.com",
        code_issued=True,
        purpose=CodePurpose.PIN_RESET,
        tries_left=2,
        pin_problem=PinProblem.UNCHANGED,
        device_token_issued=True,
    )


def test_the_released_map_covers_every_outcome() -> None:
    assert set(_EXPECTED) == set(AuthOutcomeKind)


@pytest.mark.parametrize("kind", list(AuthOutcomeKind))
def test_every_outcome_maps_to_its_released_envelope(kind: AuthOutcomeKind) -> None:
    assert envelope_for(_outcome(kind)) == _EXPECTED[kind]


def test_silent_and_issued_codes_look_the_same() -> None:
    issued = envelope_for(AuthOutcome(AuthOutcomeKind.CHECK_EMAIL, email="a@b.c"))
    silent = envelope_for(AuthOutcome(AuthOutcomeKind.SILENT))
    assert issued == silent


def test_a_refused_new_pin_on_a_released_route_discloses_only_the_floor() -> None:
    assert invalid_pin_answer() == AuthEnvelope(EnvelopeStatus.INVALID_PIN, minimum_pin_length=4)


def test_a_refused_new_pin_on_a_new_route_names_its_problem() -> None:
    assert invalid_pin_step(PinProblem.WEAK) == AuthEnvelope(
        EnvelopeStatus.INVALID_PIN, minimum_pin_length=4, pin_problem=PinProblem.WEAK
    )


_STEP = {
    AuthOutcomeKind.AUTHENTICATED: AuthEnvelope(EnvelopeStatus.AUTHENTICATED),
    AuthOutcomeKind.VERIFICATION_REQUIRED: AuthEnvelope(
        EnvelopeStatus.VERIFICATION_REQUIRED,
        masked_email="j***@example.com",
        purpose=CodePurpose.PIN_RESET,
    ),
    AuthOutcomeKind.CHECK_EMAIL: AuthEnvelope(
        EnvelopeStatus.VERIFICATION_REQUIRED,
        masked_email="j***@example.com",
        purpose=CodePurpose.PIN_RESET,
    ),
    AuthOutcomeKind.SILENT: AuthEnvelope(
        EnvelopeStatus.VERIFICATION_REQUIRED,
        masked_email="j***@example.com",
        purpose=CodePurpose.PIN_RESET,
    ),
    AuthOutcomeKind.CODE_VERIFIED: AuthEnvelope(EnvelopeStatus.CODE_VERIFIED),
    AuthOutcomeKind.INVALID_PIN: AuthEnvelope(
        EnvelopeStatus.INVALID_PIN, minimum_pin_length=4, pin_problem=PinProblem.UNCHANGED
    ),
    AuthOutcomeKind.REFUSED: AuthEnvelope(EnvelopeStatus.AUTHENTICATION_FAILED, tries_left=2),
    AuthOutcomeKind.DEVICE_REVOKED: AuthEnvelope(EnvelopeStatus.DEVICE_REVOKED),
    AuthOutcomeKind.PIN_REQUIRED: AuthEnvelope(EnvelopeStatus.PIN_REQUIRED),
    AuthOutcomeKind.PIN_LOCKED: AuthEnvelope(EnvelopeStatus.PIN_LOCKED),
    AuthOutcomeKind.BLOCKED: AuthEnvelope(EnvelopeStatus.BLOCKED),
    AuthOutcomeKind.CODE_RESENT: AuthEnvelope(
        EnvelopeStatus.CODE_RESENT, purpose=CodePurpose.PIN_RESET
    ),
    AuthOutcomeKind.PIN_CHANGED: AuthEnvelope(EnvelopeStatus.PIN_CHANGED),
}


@pytest.mark.parametrize("kind", list(_STEP))
def test_every_step_outcome_maps_to_its_step_envelope(kind: AuthOutcomeKind) -> None:
    assert step_envelope_for(_outcome(kind)) == _STEP[kind]


def test_the_step_envelope_can_leave_the_masked_address_out() -> None:
    outcome = _outcome(AuthOutcomeKind.SILENT)
    assert step_envelope_for(outcome, masked=False).masked_email is None


def _state(
    status: UserStatus = UserStatus.ACTIVE,
    pin_hash: str | None = "s.k",
    *,
    reset: bool = False,
) -> AccountState:
    return AccountState(
        user_id=uuid4(),
        status=status,
        pin_hash=pin_hash,
        phone_number="+254712345678",
        security_version=0,
        failed_attempts=0,
        untrusted_failed_attempts=0,
        pin_reset_required=reset,
        device_trusted=True,
        policy=None,
    )


def test_dummy_hash_rule() -> None:
    assert needs_dummy_hash(None) is True
    assert needs_dummy_hash(_state(status=UserStatus.REMOVED)) is True
    assert needs_dummy_hash(_state(pin_hash=None)) is True
    assert needs_dummy_hash(_state(reset=True)) is True
    assert needs_dummy_hash(_state()) is False


def test_secrets_stay_out_of_the_envelope_repr() -> None:
    envelope = AuthEnvelope(
        EnvelopeStatus.AUTHENTICATED,
        access_token="access-secret",
        refresh_token="refresh-secret",
        development_code="482913",
        device_token="device-secret",
    )
    text = repr(envelope)
    for secret in ("access-secret", "refresh-secret", "482913", "device-secret"):
        assert secret not in text
    assert "+254712345678" not in repr(_state())
