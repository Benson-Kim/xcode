"""Remove one of the signed-in person's own trusted devices by its id
(``POST /auth/trusted-devices/{id}/remove``); a device that is not theirs and live is
``NotFound``."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.identity import AuthEnvelope, DeviceRemoval
from ...domain.policies import step_envelope_for
from ..ports import Clock
from ..repositories import IdentityRepository


@dataclass(frozen=True, slots=True)
class RemoveTrustedDeviceCommand:
    request_id: str
    user_id: UUID
    row_id: UUID


class RemoveTrustedDevice:
    def __init__(self, identity: IdentityRepository, clock: Clock) -> None:
        self._identity = identity
        self._clock = clock

    async def execute(self, command: RemoveTrustedDeviceCommand) -> AuthEnvelope:
        outcome = await self._identity.device_remove(
            DeviceRemoval(command.request_id, command.user_id, command.row_id, self._clock.now())
        )
        return step_envelope_for(outcome)
