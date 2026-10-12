"""Auth decisions that span two statements against the real database: a change that
commits between the sign-in lookup and its decision routine (``docs/07-auth.md`` section
3.1)."""

from __future__ import annotations

import pytest

from xcode_api.settings import PIN_ITERATIONS_TESTING

from ..support.client import DEVICE, PHONE, PIN, ApiFactory, code_of, envelope
from ..support.pins import HasherWithPause
from ..support.scenario import live_tokens, user_row

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEW_PIN = "8642"
OTHER_DEVICE = "tablet-9"


async def test_a_pin_reset_during_a_sign_in_voids_the_old_pins_verdict(
    make_api: ApiFactory,
) -> None:
    api = await make_api()
    user_id, _ = await api.onboard()
    racing_hasher = HasherWithPause(PIN_ITERATIONS_TESTING)
    racing = await make_api(pin_hasher=racing_hasher)

    async def reset_the_pin() -> None:
        before = len(api.mail.sent)
        await api.post("/auth/pin-reset/request", phoneNumber=PHONE, deviceId=OTHER_DEVICE)
        await api.delivered(before + 1)
        code = code_of(api.mail.sent[-1].text)
        envelope(
            await api.post(
                "/auth/pin-reset/complete",
                phoneNumber=PHONE,
                pin=NEW_PIN,
                code=code,
                deviceId=OTHER_DEVICE,
            ),
            200,
            "authenticated",
        )

    # The old PIN is checked against the hash the lookup read; the reset commits meanwhile.
    racing_hasher.before_verify = reset_the_pin
    envelope(await racing.sign_in(pin=PIN, device=DEVICE), 401, "authentication_failed")
    assert live_tokens(api.owner, user_id, DEVICE) == 0
    # The reset removed the old phone, so the voided verdict counts as an untrusted wrong PIN.
    row = user_row(api.owner, user_id)
    assert (row["failed_attempts"], row["untrusted_failed_attempts"]) == (0, 1)
    envelope(await api.sign_in(pin=NEW_PIN, device=OTHER_DEVICE), 200, "authenticated")
