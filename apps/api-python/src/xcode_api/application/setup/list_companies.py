"""One page of the companies the caller may see."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.setup import CompanyPage, SetupPageQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class ListCompaniesQuery:
    caller: Caller
    page: int
    page_size: int


class ListCompanies:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: ListCompaniesQuery) -> CompanyPage:
        return await self._setup.list_companies(
            SetupPageQuery(query.caller.context(self._clock), query.page, query.page_size)
        )
