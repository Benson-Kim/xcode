"""Add a vehicle with its fleet number and its first target set."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.setup import VehicleDetails, VehicleSave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class CreateVehicleCommand:
    caller: Caller
    details: VehicleDetails
    reason: str | None


class CreateVehicle:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: CreateVehicleCommand) -> WriteResult:
        return await self._setup.create_vehicle(
            VehicleSave(command.caller.context(self._clock), None, command.details, command.reason)
        )
