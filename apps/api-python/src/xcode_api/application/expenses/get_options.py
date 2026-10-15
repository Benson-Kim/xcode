"""What the central-expense form picks from on a date."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...domain.expenses import ExpenseOptions, ExpenseOptionsQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import ExpensesRepository


@dataclass(frozen=True, slots=True)
class GetExpenseOptionsQuery:
    caller: Caller
    day: date | None


class GetExpenseOptions:
    def __init__(self, expenses: ExpensesRepository, clock: Clock) -> None:
        self._expenses = expenses
        self._clock = clock

    async def execute(self, query: GetExpenseOptionsQuery) -> ExpenseOptions:
        return await self._expenses.options(
            ExpenseOptionsQuery(query.caller.context(self._clock), query.day)
        )
