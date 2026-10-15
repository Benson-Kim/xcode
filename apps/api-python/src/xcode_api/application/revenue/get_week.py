"""The revenue week grid, one page of it, or one vehicle in any week."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.revenue import RevenueWeek, RevenueWeekQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import RevenueRepository


@dataclass(frozen=True, slots=True)
class GetRevenueWeekQuery:
    caller: Caller
    week_start: date | None
    company_id: UUID | None
    vehicle_id: UUID | None
    page: int | None
    page_size: int | None
    q: str | None = None


class GetRevenueWeek:
    def __init__(self, revenue: RevenueRepository, clock: Clock) -> None:
        self._revenue = revenue
        self._clock = clock

    async def execute(self, query: GetRevenueWeekQuery) -> RevenueWeek:
        return await self._revenue.week(
            RevenueWeekQuery(
                query.caller.context(self._clock),
                query.week_start,
                query.company_id,
                query.vehicle_id,
                query.page,
                query.page_size,
                query.q,
            )
        )
