"""One page of the central-expenses ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...domain.expenses import ExpenseLedger, ExpenseLedgerQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import ExpensesRepository


@dataclass(frozen=True, slots=True)
class GetExpenseLedgerQuery:
    caller: Caller
    from_date: date | None
    to_date: date | None
    source: str | None
    q: str | None
    page: int
    page_size: int


class GetExpenseLedger:
    def __init__(self, expenses: ExpensesRepository, clock: Clock) -> None:
        self._expenses = expenses
        self._clock = clock

    async def execute(self, query: GetExpenseLedgerQuery) -> ExpenseLedger:
        return await self._expenses.ledger(
            ExpenseLedgerQuery(
                query.caller.context(self._clock),
                query.from_date,
                query.to_date,
                query.source,
                query.q,
                query.page,
                query.page_size,
            )
        )
