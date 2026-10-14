"""Remove one central expense row, softly, with a reason."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.expenses import ExpenseRemoval, ExpenseSaved
from ..caller import Caller
from ..ports import Clock
from ..repositories import ExpensesRepository


@dataclass(frozen=True, slots=True)
class RemoveExpenseCommand:
    caller: Caller
    entry_id: UUID
    version: int | None
    reason: str | None


class RemoveExpense:
    def __init__(self, expenses: ExpensesRepository, clock: Clock) -> None:
        self._expenses = expenses
        self._clock = clock

    async def execute(self, command: RemoveExpenseCommand) -> ExpenseSaved:
        return await self._expenses.remove(
            ExpenseRemoval(
                command.caller.context(self._clock),
                command.entry_id,
                command.version,
                command.reason,
            )
        )
