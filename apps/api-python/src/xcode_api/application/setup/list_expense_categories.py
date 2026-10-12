"""One page of the expense categories with their items."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.setup import ExpenseCategoryPage, SetupPageQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class ListExpenseCategoriesQuery:
    caller: Caller
    page: int
    page_size: int


class ListExpenseCategories:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: ListExpenseCategoriesQuery) -> ExpenseCategoryPage:
        return await self._setup.list_expense_categories(
            SetupPageQuery(query.caller.context(self._clock), query.page, query.page_size)
        )
