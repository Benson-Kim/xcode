"""Cancel a stop that has not taken effect yet."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import RecurringCancelStop
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class CancelRecurringStopCommand:
    caller: Caller
    item_id: UUID


class CancelRecurringStop:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: CancelRecurringStopCommand) -> WriteResult:
        return await self._setup.cancel_recurring_stop(
            RecurringCancelStop(command.caller.context(self._clock), command.item_id)
        )
