"""Turn an expense item off from the business date, or on again."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import ExpenseLifecycle
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class SetExpenseItemStoppedCommand:
    caller: Caller
    item_id: UUID
    stopped: bool


class SetExpenseItemStopped:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: SetExpenseItemStoppedCommand) -> WriteResult:
        return await self._setup.set_expense_item_stopped(
            ExpenseLifecycle(command.caller.context(self._clock), command.item_id, command.stopped)
        )
