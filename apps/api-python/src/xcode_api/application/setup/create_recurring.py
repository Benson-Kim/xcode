"""Add a scheduled expense or saving."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.setup import RecurringDefinition, RecurringSave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class CreateRecurringCommand:
    caller: Caller
    definition: RecurringDefinition
    reason: str | None


class CreateRecurring:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: CreateRecurringCommand) -> WriteResult:
        return await self._setup.create_recurring(
            RecurringSave(
                command.caller.context(self._clock), None, command.definition, command.reason
            )
        )
