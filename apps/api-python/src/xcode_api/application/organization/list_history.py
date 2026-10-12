"""The change log the caller may see, filtered and paged."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import HistoryFilter, HistoryPage, HistoryQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class ListHistoryQuery:
    caller: Caller
    filter: HistoryFilter


class ListHistory:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, query: ListHistoryQuery) -> HistoryPage:
        return await self._tenancy.list_history(
            HistoryQuery(query.caller.context(self._clock), query.filter)
        )
