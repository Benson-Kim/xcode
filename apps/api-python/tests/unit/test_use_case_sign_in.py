"""``SignIn`` orchestration: lookup, exactly one PBKDF2 derivation, the decision routine,
then tokens or the new-device mail (awaited, withdrawn on failure)."""

from __future__ import annotations

import pytest

from xcode_api.application.auth.sign_in import SignInCommand
from xcode_api.application.errors import TransientFailure
from xcode_api.domain.identity import (
    AuthEnvelope,
    CodePurpose,
    EnvelopeStatus,
    UserStatus,
)
from xcode_api.domain.policies import refusal_answer, service_unavailable_answer

from ..support.fakes import PinHasherSpy
from ..support.pins import HasherAtCapacity
from .conftest import LOW_ITERATIONS, PIN, TRUSTED, AuthKit

NEW_DEVICE = "tablet-9"


def _command(pin: str = PIN, device: str = TRUSTED, phone: str = "0712345678") -> SignInCommand:
    return SignInCommand("req-1", phone, pin, device)


async def test_a_right_pin_on_a_trusted_device_returns_the_token_pair(kit: AuthKit) -> None:
    user_id = await kit.account()
    envelope = await kit.sign_in().execute(_command())

    assert kit.calls == ["account_lookup", "pins.verify", "sign_in"]
    assert envelope.status is EnvelopeStatus.AUTHENTICATED
    assert envelope.refresh_token == kit.secrets.refresh_tokens[0]
    assert envelope.access_token is not None
    claims = kit.tokens.verify(envelope.access_token, now=kit.clock.now())
    assert (claims.user_id, claims.device_id, claims.role) == (user_id, TRUSTED, "Owner")
    stored = [t.token_hash for t in kit.identity.tokens(user_id)]
    assert stored == [kit.digest(envelope.refresh_token)]


async def test_an_unknown_number_still_costs_one_derivation(kit: AuthKit) -> None:
    envelope = await kit.sign_in().execute(_command(phone="0799999999"))
    assert kit.calls == ["account_lookup", "pins.dummy_verify", "sign_in"]
    assert kit.pins.derivations == 1
    assert envelope is refusal_answer()


async def test_a_number_that_does_not_normalise_costs_one_derivation(kit: AuthKit) -> None:
    await kit.account()
    envelope = await kit.sign_in().execute(_command(phone="not a number"))
    assert kit.calls == ["account_lookup", "pins.dummy_verify", "sign_in"]
    assert envelope is refusal_answer()


async def test_removed_and_pinless_accounts_use_the_dummy_hash(kit: AuthKit) -> None:
    removed = await kit.account()
    kit.identity.set_user(removed, status=UserStatus.REMOVED)
    assert await kit.sign_in().execute(_command()) is refusal_answer()
    await kit.account(pin=None, phone="0722222222", email="b@example.com")
    assert await kit.sign_in().execute(_command(phone="0722222222")) is refusal_answer()
    assert [c for c in kit.calls if c.startswith("pins.")] == [
        "pins.dummy_verify",
        "pins.dummy_verify",
    ]


async def test_a_wrong_pin_costs_exactly_one_derivation(kit: AuthKit) -> None:
    user_id = await kit.account()
    envelope = await kit.sign_in().execute(_command(pin="9999"))
    assert kit.calls == ["account_lookup", "pins.verify", "sign_in"]
    assert envelope is refusal_answer()
    assert kit.identity.user(user_id).failed_attempts == 1


async def test_a_new_device_gets_its_code_mailed_before_the_reply(kit: AuthKit) -> None:
    user_id = await kit.account()
    envelope = await kit.sign_in().execute(_command(device=NEW_DEVICE))

    assert kit.calls == ["account_lookup", "pins.verify", "sign_in", "mail.send_now"]
    assert envelope == AuthEnvelope(
        EnvelopeStatus.VERIFICATION_REQUIRED, masked_email="j***@example.com"
    )
    (mail,) = kit.mail.mails
    (code,) = kit.identity.codes(user_id)
    assert (mail.to, mail.purpose, mail.code, mail.code_id, mail.request_id) == (
        "jane.doe@example.com",
        CodePurpose.NEW_DEVICE,
        kit.secrets.code,
        code.code_id,
        "req-1",
    )
    assert code.code_hash == kit.digest(kit.secrets.code)
    assert kit.identity.tokens(user_id) == []


async def test_a_failed_new_device_mail_withdraws_the_code(kit: AuthKit) -> None:
    user_id = await kit.account()
    kit.mail.deliver = False
    envelope = await kit.sign_in().execute(_command(device=NEW_DEVICE))

    assert kit.calls == [
        "account_lookup",
        "pins.verify",
        "sign_in",
        "mail.send_now",
        "withdraw_code",
    ]
    assert envelope is service_unavailable_answer()
    (code,) = kit.identity.codes(user_id)
    assert code.withdrawn


async def test_inside_the_cooldown_no_code_is_mailed_and_the_answer_is_the_same(
    kit: AuthKit,
) -> None:
    await kit.account()
    first = await kit.sign_in().execute(_command(device=NEW_DEVICE))
    kit.calls.clear()
    kit.clock.advance(30)
    second = await kit.sign_in().execute(_command(device=NEW_DEVICE))
    assert kit.calls == ["account_lookup", "pins.verify", "sign_in"]
    assert second == first
    assert second.development_code is None


async def test_development_codes_return_the_code_and_skip_the_cooldown(kit: AuthKit) -> None:
    await kit.account()
    use_case = kit.sign_in(development_codes=True)
    first = await use_case.execute(_command(device=NEW_DEVICE))
    kit.clock.advance(30)
    second = await use_case.execute(_command(device=NEW_DEVICE))
    assert first.development_code == kit.secrets.code
    assert second.development_code == kit.secrets.code
    assert kit.calls.count("mail.send_now") == 2


async def test_a_locked_trusted_device_shows_the_policy_pause(kit: AuthKit) -> None:
    user_id = await kit.account()
    kit.identity.set_user(user_id, failed_attempts=5)
    envelope = await kit.sign_in().execute(_command())
    assert envelope == AuthEnvelope(EnvelopeStatus.PAUSED, retry_after_seconds=900)
    assert kit.pins.derivations == 1


def test_the_command_repr_carries_neither_pin_nor_number() -> None:
    text = repr(SignInCommand("req-1", "0712345678", "5826", "phone-1"))
    assert "5826" not in text
    assert "712345678" not in text


async def test_a_full_pin_hasher_stops_sign_in_before_the_decision(kit: AuthKit) -> None:
    user_id = await kit.account()
    kit.pins = PinHasherSpy(HasherAtCapacity(LOW_ITERATIONS), kit.calls)
    for phone in ("0712345678", "0799999999"):
        with pytest.raises(TransientFailure):
            await kit.sign_in().execute(_command(pin="9999", phone=phone))
    assert kit.calls == ["account_lookup", "account_lookup"]
    assert kit.identity.user(user_id).failed_attempts == 0
