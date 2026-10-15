"""Stop a scheduled item from the business date; the caller confirms and says why."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import RecurringStop
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class StopRecurringCommand:
    caller: Caller
    item_id: UUID
    confirmed: bool | None
    reason: str | None


class StopRecurring:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: StopRecurringCommand) -> WriteResult:
        return await self._setup.stop_recurring(
            RecurringStop(
                command.caller.context(self._clock),
                command.item_id,
                command.confirmed,
                command.reason,
            )
        )
