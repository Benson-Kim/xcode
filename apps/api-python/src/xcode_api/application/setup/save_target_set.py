"""Give a vehicle a target set from today or later."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from ...domain.setup import TargetSetSave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class SaveTargetSetCommand:
    caller: Caller
    vehicle_id: UUID
    starts_on: date | None
    days: tuple[Decimal | None, ...] | None


class SaveTargetSet:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: SaveTargetSetCommand) -> WriteResult:
        return await self._setup.save_target_set(
            TargetSetSave(
                command.caller.context(self._clock),
                command.vehicle_id,
                command.starts_on,
                command.days,
            )
        )
