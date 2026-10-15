"""``RevokeDevice`` orchestration: one routine call for the caller's own device."""

from __future__ import annotations

from xcode_api.application.auth.revoke_device import RevokeDeviceCommand
from xcode_api.domain.identity import AuthEnvelope, EnvelopeStatus

from .conftest import TRUSTED, AuthKit


async def test_revoking_the_own_device_answers_device_revoked(kit: AuthKit) -> None:
    user_id = await kit.account()
    envelope = await kit.revoke_device().execute(RevokeDeviceCommand("req-10", user_id, TRUSTED))
    assert kit.calls == ["revoke_device"]
    assert envelope == AuthEnvelope(EnvelopeStatus.DEVICE_REVOKED)
    (device,) = kit.identity.devices(user_id)
    assert device.revoked
