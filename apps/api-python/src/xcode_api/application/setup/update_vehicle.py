"""Change a vehicle's company, join date, fleet number or initial investment."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import VehicleDetails, VehicleSave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class UpdateVehicleCommand:
    caller: Caller
    vehicle_id: UUID
    details: VehicleDetails
    reason: str | None


class UpdateVehicle:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: UpdateVehicleCommand) -> WriteResult:
        return await self._setup.update_vehicle(
            VehicleSave(
                command.caller.context(self._clock),
                command.vehicle_id,
                command.details,
                command.reason,
            )
        )
