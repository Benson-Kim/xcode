"""Remove one trusted device of a person at once."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import PersonDeviceRemoval
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class RemovePersonDeviceCommand:
    caller: Caller
    user_id: UUID
    device_id: UUID


class RemovePersonDevice:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: RemovePersonDeviceCommand) -> WriteResult:
        return await self._tenancy.remove_person_device(
            PersonDeviceRemoval(
                command.caller.context(self._clock), command.user_id, command.device_id
            )
        )
