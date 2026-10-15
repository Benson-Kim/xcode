"""``VerifyCode`` orchestration: one routine call with the code digest; the code is kept."""

from __future__ import annotations

from xcode_api.application.auth.verify_code import VerifyCodeCommand
from xcode_api.domain.identity import AuthEnvelope, CodePurpose, EnvelopeStatus
from xcode_api.domain.policies import refusal_answer

from .conftest import AuthKit


async def test_a_matching_code_is_verified_and_kept(kit: AuthKit) -> None:
    user_id = await kit.account(pin=None, trusted=())
    kit.identity.store_code(
        user_id,
        CodePurpose.FIRST_SETUP,
        "phone-1",
        kit.digest("048213"),
        created_at=kit.clock.now(),
    )
    envelope = await kit.verify_code().execute(
        VerifyCodeCommand("req-4", "0712345678", "048213", "phone-1", CodePurpose.FIRST_SETUP)
    )
    assert kit.calls == ["verify_code"]
    assert envelope == AuthEnvelope(EnvelopeStatus.CODE_VERIFIED)
    assert not kit.identity.codes(user_id)[0].consumed


async def test_another_purpose_or_device_is_refused(kit: AuthKit) -> None:
    user_id = await kit.account(pin=None, trusted=())
    kit.identity.store_code(
        user_id,
        CodePurpose.FIRST_SETUP,
        "phone-1",
        kit.digest("048213"),
        created_at=kit.clock.now(),
    )
    other_device = await kit.verify_code().execute(
        VerifyCodeCommand("req-4", "0712345678", "048213", "phone-2", CodePurpose.FIRST_SETUP)
    )
    other_purpose = await kit.verify_code().execute(
        VerifyCodeCommand("req-4", "0712345678", "048213", "phone-1", CodePurpose.PIN_RESET)
    )
    assert other_device is refusal_answer()
    assert other_purpose is refusal_answer()
