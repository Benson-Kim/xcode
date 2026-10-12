"""Take a vehicle out of the fleet from a date."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.setup import VehicleRetirement
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class RetireVehicleCommand:
    caller: Caller
    vehicle_id: UUID
    left_on: date | None
    reason: str | None


class RetireVehicle:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: RetireVehicleCommand) -> WriteResult:
        return await self._setup.retire_vehicle(
            VehicleRetirement(
                command.caller.context(self._clock),
                command.vehicle_id,
                command.left_on,
                command.reason,
            )
        )
