"""``CompletePin`` orchestration: the PIN shape is checked before any port is told anything;
then one hash and one routine call; the policy minimum comes only from the routine."""

from __future__ import annotations

from uuid import UUID

import pytest

from xcode_api.application.auth.complete_pin import CompletePinCommand
from xcode_api.application.errors import TransientFailure
from xcode_api.domain.identity import AuthEnvelope, CodePurpose, EnvelopeStatus
from xcode_api.domain.policies import refusal_answer

from ..support.fakes import PinHasherSpy
from ..support.pins import HasherAtCapacity
from .conftest import LOW_ITERATIONS, AuthKit


def _command(pin: str, code: str = "048213") -> CompletePinCommand:
    return CompletePinCommand("req-5", "0712345678", pin, code, "phone-1", CodePurpose.FIRST_SETUP)


async def _with_code(kit: AuthKit) -> UUID:
    user_id = await kit.account(pin=None, trusted=())
    kit.identity.store_code(
        user_id,
        CodePurpose.FIRST_SETUP,
        "phone-1",
        kit.digest("048213"),
        created_at=kit.clock.now(),
    )
    return user_id


async def test_a_bad_shape_is_refused_before_any_port_is_told(kit: AuthKit) -> None:
    await _with_code(kit)
    for pin in ("123", "1111", "1234", "58a6"):
        envelope = await kit.complete_pin().execute(_command(pin))
        assert envelope == AuthEnvelope(EnvelopeStatus.INVALID_PIN, minimum_pin_length=4)
    assert kit.calls == []


async def test_a_valid_pin_is_hashed_once_then_stored_by_the_routine(kit: AuthKit) -> None:
    user_id = await _with_code(kit)
    envelope = await kit.complete_pin().execute(_command("5826"))

    assert kit.calls == ["pins.hash", "complete_pin"]
    assert envelope.status is EnvelopeStatus.AUTHENTICATED
    assert envelope.refresh_token == kit.secrets.refresh_tokens[0]
    stored = kit.identity.user(user_id).pin_hash
    assert stored is not None
    assert await kit.hasher.verify("5826", stored)


async def test_every_new_pin_is_four_digits_whatever_the_organization_pin_length(
    kit: AuthKit,
) -> None:
    user_id = await _with_code(kit)
    kit.identity.set_policy(kit.identity.user(user_id).organization_id, pin_length=6)
    longer = await kit.complete_pin().execute(_command("582613"))
    assert longer == AuthEnvelope(EnvelopeStatus.INVALID_PIN, minimum_pin_length=4)
    wrong_code = await kit.complete_pin().execute(_command("5826", code="111111"))
    assert wrong_code is refusal_answer()
    accepted = await kit.complete_pin().execute(_command("5826"))
    assert accepted.status is EnvelopeStatus.AUTHENTICATED


async def test_a_full_pin_hasher_stops_the_new_pin_before_the_routine(kit: AuthKit) -> None:
    user_id = await _with_code(kit)
    kit.pins = PinHasherSpy(HasherAtCapacity(LOW_ITERATIONS), kit.calls)
    with pytest.raises(TransientFailure):
        await kit.complete_pin().execute(_command("5826"))
    assert kit.calls == []

    kit.pins = PinHasherSpy(kit.hasher, kit.calls)
    retried = await kit.complete_pin().execute(_command("5826"))
    assert retried.status is EnvelopeStatus.AUTHENTICATED, "the refused request spent the code"
    assert kit.identity.user(user_id).pin_hash is not None
