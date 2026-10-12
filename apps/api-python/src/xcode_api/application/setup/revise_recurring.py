"""Save a new version of a scheduled expense or saving."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import RecurringDefinition, RecurringSave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class ReviseRecurringCommand:
    caller: Caller
    item_id: UUID
    definition: RecurringDefinition
    reason: str | None


class ReviseRecurring:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: ReviseRecurringCommand) -> WriteResult:
        return await self._setup.revise_recurring(
            RecurringSave(
                command.caller.context(self._clock),
                command.item_id,
                command.definition,
                command.reason,
            )
        )
