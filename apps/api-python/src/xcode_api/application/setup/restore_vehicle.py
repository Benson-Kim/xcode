"""Bring a vehicle back into the fleet; no date means the business date."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.setup import VehicleReturn
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class RestoreVehicleCommand:
    caller: Caller
    vehicle_id: UUID
    returned_on: date | None
    reason: str | None


class RestoreVehicle:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: RestoreVehicleCommand) -> WriteResult:
        return await self._setup.restore_vehicle(
            VehicleReturn(
                command.caller.context(self._clock),
                command.vehicle_id,
                command.returned_on,
                command.reason,
            )
        )
