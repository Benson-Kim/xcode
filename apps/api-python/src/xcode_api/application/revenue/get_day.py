"""One day of the visible fleet, for capturing it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.revenue import RevenueDay, RevenueDayQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import RevenueRepository


@dataclass(frozen=True, slots=True)
class GetRevenueDayQuery:
    caller: Caller
    day: date | None
    company_id: UUID | None


class GetRevenueDay:
    def __init__(self, revenue: RevenueRepository, clock: Clock) -> None:
        self._revenue = revenue
        self._clock = clock

    async def execute(self, query: GetRevenueDayQuery) -> RevenueDay:
        return await self._revenue.day(
            RevenueDayQuery(query.caller.context(self._clock), query.day, query.company_id)
        )
