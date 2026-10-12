"""The revenue dashboard cards for today, the week or the month."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.revenue import RevenueDashboard, RevenueDashboardQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import RevenueRepository


@dataclass(frozen=True, slots=True)
class GetRevenueDashboardQuery:
    caller: Caller
    period: str | None
    company_id: UUID | None


class GetRevenueDashboard:
    def __init__(self, revenue: RevenueRepository, clock: Clock) -> None:
        self._revenue = revenue
        self._clock = clock

    async def execute(self, query: GetRevenueDashboardQuery) -> RevenueDashboard:
        return await self._revenue.dashboard(
            RevenueDashboardQuery(query.caller.context(self._clock), query.period, query.company_id)
        )
