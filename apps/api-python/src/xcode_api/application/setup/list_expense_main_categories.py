"""One page of the main categories with their counts."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.setup import MainCategoryPage, SetupPageQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class ListExpenseMainCategoriesQuery:
    caller: Caller
    page: int
    page_size: int


class ListExpenseMainCategories:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: ListExpenseMainCategoriesQuery) -> MainCategoryPage:
        return await self._setup.list_expense_main_categories(
            SetupPageQuery(query.caller.context(self._clock), query.page, query.page_size)
        )
