"""``Refresh`` orchestration: the presented token's digest and its replacement's digest go
to one routine call; the replacement is what the client gets back."""

from __future__ import annotations

from datetime import timedelta

from xcode_api.application.auth.refresh import RefreshCommand
from xcode_api.domain.identity import EnvelopeStatus
from xcode_api.domain.policies import refusal_answer

from .conftest import TRUSTED, AuthKit


async def test_rotation_returns_the_replacement_and_replay_is_refused(kit: AuthKit) -> None:
    user_id = await kit.account()
    kit.identity.store_token(
        user_id,
        TRUSTED,
        kit.digest("presented-token"),
        expires_at=kit.clock.now() + timedelta(days=30),
    )
    rotated = await kit.refresh().execute(RefreshCommand("req-6", "presented-token", TRUSTED))

    assert kit.calls == ["refresh"]
    assert rotated.status is EnvelopeStatus.AUTHENTICATED
    assert rotated.refresh_token == kit.secrets.refresh_tokens[0]
    assert rotated.access_token is not None
    assert kit.identity.live_tokens(user_id, TRUSTED) == 1

    replayed = await kit.refresh().execute(RefreshCommand("req-7", "presented-token", TRUSTED))
    assert replayed is refusal_answer()
    assert kit.identity.live_tokens(user_id, TRUSTED) == 0


async def test_an_unknown_token_is_the_uniform_refusal(kit: AuthKit) -> None:
    await kit.account()
    envelope = await kit.refresh().execute(RefreshCommand("req-6", "never-issued", TRUSTED))
    assert envelope is refusal_answer()
