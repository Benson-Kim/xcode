"""The signed-in person's own trusted devices (``GET /auth/trusted-devices``), the one in use
marked."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.identity import DeviceListing, TrustedDeviceView
from ..ports import Clock
from ..repositories import IdentityRepository


@dataclass(frozen=True, slots=True)
class ListTrustedDevicesQuery:
    user_id: UUID
    device_id: str


class ListTrustedDevices:
    def __init__(self, identity: IdentityRepository, clock: Clock) -> None:
        self._identity = identity
        self._clock = clock

    async def execute(self, query: ListTrustedDevicesQuery) -> tuple[TrustedDeviceView, ...]:
        return await self._identity.device_list(
            DeviceListing(query.user_id, query.device_id, self._clock.now())
        )
