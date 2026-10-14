"""Record one purchase for one to fifty vehicles; a retried purchase answers its rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from ...domain.expenses import ExpenseAllocation, ExpensePurchase, ExpenseRecorded
from ..caller import Caller
from ..ports import Clock
from ..repositories import ExpensesRepository


@dataclass(frozen=True, slots=True)
class RecordExpenseCommand:
    caller: Caller
    id: UUID | None
    day: date | None
    expense_item_id: UUID | None
    units: Decimal | None
    unit_amount: Decimal | None
    note: str | None
    allocations: tuple[ExpenseAllocation, ...] | None


class RecordExpense:
    def __init__(self, expenses: ExpensesRepository, clock: Clock) -> None:
        self._expenses = expenses
        self._clock = clock

    async def execute(self, command: RecordExpenseCommand) -> ExpenseRecorded:
        return await self._expenses.record(
            ExpensePurchase(
                command.caller.context(self._clock),
                command.id,
                command.day,
                command.expense_item_id,
                command.units,
                command.unit_amount,
                command.note,
                command.allocations,
            )
        )
