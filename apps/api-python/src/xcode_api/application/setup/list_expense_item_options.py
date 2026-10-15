"""The expense items in use that a cost can be for."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.setup import ExpenseItemChoice
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class ListExpenseItemOptionsQuery:
    caller: Caller


class ListExpenseItemOptions:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: ListExpenseItemOptionsQuery) -> tuple[ExpenseItemChoice, ...]:
        return await self._setup.expense_item_options(query.caller.context(self._clock))
