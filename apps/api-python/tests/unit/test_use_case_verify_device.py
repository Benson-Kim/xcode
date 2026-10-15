"""``VerifyDevice`` orchestration: one routine call with the code digest and the digest of
the refresh token it then returns; no PBKDF2."""

from __future__ import annotations

from datetime import timedelta

from xcode_api.application.auth.verify_device import VerifyDeviceCommand
from xcode_api.domain.identity import CodePurpose, EnvelopeStatus
from xcode_api.domain.policies import refusal_answer

from .conftest import AuthKit


async def test_a_valid_code_trusts_the_device_and_returns_the_pair(kit: AuthKit) -> None:
    user_id = await kit.account(trusted=())
    kit.identity.store_code(
        user_id,
        CodePurpose.NEW_DEVICE,
        "tablet-9",
        kit.digest("048213"),
        created_at=kit.clock.now(),
    )
    envelope = await kit.verify_device(trust_days=30).execute(
        VerifyDeviceCommand("req-3", "0712345678", "048213", "tablet-9")
    )

    assert kit.calls == ["verify_device"]
    assert envelope.status is EnvelopeStatus.AUTHENTICATED
    assert envelope.refresh_token == kit.secrets.refresh_tokens[0]
    assert envelope.access_token is not None
    assert kit.tokens.verify(envelope.access_token, now=kit.clock.now()).device_id == "tablet-9"
    (device,) = kit.identity.devices(user_id)
    assert device.trust_expires_at == kit.clock.now() + timedelta(days=30)
    assert kit.pins.derivations == 0


async def test_a_wrong_code_is_the_uniform_refusal(kit: AuthKit) -> None:
    user_id = await kit.account(trusted=())
    kit.identity.store_code(
        user_id,
        CodePurpose.NEW_DEVICE,
        "tablet-9",
        kit.digest("048213"),
        created_at=kit.clock.now(),
    )
    envelope = await kit.verify_device().execute(
        VerifyDeviceCommand("req-3", "0712345678", "111111", "tablet-9")
    )
    assert envelope is refusal_answer()
    assert kit.identity.codes(user_id)[0].failed_attempts == 1
