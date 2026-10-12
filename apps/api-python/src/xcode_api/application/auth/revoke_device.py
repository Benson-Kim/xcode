"""Revoke the caller's own device (``POST /auth/devices/{id}/revoke``); always
``device_revoked``. The router has already refused any device but the token's own."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.identity import AuthEnvelope, DeviceRevocation
from ...domain.policies import envelope_for
from ..ports import Clock
from ..repositories import IdentityRepository


@dataclass(frozen=True, slots=True)
class RevokeDeviceCommand:
    request_id: str
    user_id: UUID
    device_id: str


class RevokeDevice:
    def __init__(self, identity: IdentityRepository, clock: Clock) -> None:
        self._identity = identity
        self._clock = clock

    async def execute(self, command: RevokeDeviceCommand) -> AuthEnvelope:
        outcome = await self._identity.revoke_device(
            DeviceRevocation(
                command.request_id, command.user_id, command.device_id, self._clock.now()
            )
        )
        return envelope_for(outcome)
