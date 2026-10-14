"""Pause a scheduled item as of the business date."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import RecurringPause
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class PauseRecurringCommand:
    caller: Caller
    item_id: UUID


class PauseRecurring:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: PauseRecurringCommand) -> WriteResult:
        return await self._setup.pause_recurring(
            RecurringPause(command.caller.context(self._clock), command.item_id)
        )
