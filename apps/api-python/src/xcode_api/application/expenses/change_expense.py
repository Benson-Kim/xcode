"""Change one central expense row."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from ...domain.expenses import ExpenseChange, ExpenseSaved
from ..caller import Caller
from ..ports import Clock
from ..repositories import ExpensesRepository


@dataclass(frozen=True, slots=True)
class ChangeExpenseCommand:
    caller: Caller
    entry_id: UUID
    day: date | None
    vehicle_id: UUID | None
    expense_item_id: UUID | None
    units: Decimal | None
    unit_amount: Decimal | None
    note: str | None
    version: int | None


class ChangeExpense:
    def __init__(self, expenses: ExpensesRepository, clock: Clock) -> None:
        self._expenses = expenses
        self._clock = clock

    async def execute(self, command: ChangeExpenseCommand) -> ExpenseSaved:
        return await self._expenses.change(
            ExpenseChange(
                command.caller.context(self._clock),
                command.entry_id,
                command.day,
                command.vehicle_id,
                command.expense_item_id,
                command.units,
                command.unit_amount,
                command.note,
                command.version,
            )
        )
