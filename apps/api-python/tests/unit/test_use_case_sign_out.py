"""``SignOut`` orchestration: one routine call with the token digest; always ``signed_out``."""

from __future__ import annotations

from datetime import timedelta

from xcode_api.application.auth.sign_out import SignOutCommand
from xcode_api.domain.identity import AuthEnvelope, EnvelopeStatus

from .conftest import TRUSTED, AuthKit

SIGNED_OUT = AuthEnvelope(EnvelopeStatus.SIGNED_OUT)


async def test_sign_out_revokes_the_devices_tokens_and_always_answers_signed_out(
    kit: AuthKit,
) -> None:
    user_id = await kit.account()
    kit.identity.store_token(
        user_id, TRUSTED, kit.digest("live-token"), expires_at=kit.clock.now() + timedelta(days=1)
    )
    known = await kit.sign_out().execute(SignOutCommand("req-8", "live-token", TRUSTED))
    unknown = await kit.sign_out().execute(SignOutCommand("req-9", "never-issued", TRUSTED))
    assert kit.calls == ["sign_out", "sign_out"]
    assert known == unknown == SIGNED_OUT
    assert kit.identity.live_tokens(user_id) == 0
