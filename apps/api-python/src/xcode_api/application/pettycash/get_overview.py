"""The petty-cash screen: the caller's rights, the floats they may see, the figures of the
chosen days and one row per float."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.pettycash import PettyCashOverview, PettyCashOverviewQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import PettyCashRepository


@dataclass(frozen=True, slots=True)
class GetPettyCashOverviewQuery:
    caller: Caller
    day: date | None
    period: str | None
    holder_id: UUID | None
    from_date: date | None
    to_date: date | None


class GetPettyCashOverview:
    def __init__(self, pettycash: PettyCashRepository, clock: Clock) -> None:
        self._pettycash = pettycash
        self._clock = clock

    async def execute(self, query: GetPettyCashOverviewQuery) -> PettyCashOverview:
        return await self._pettycash.overview(
            PettyCashOverviewQuery(
                query.caller.context(self._clock),
                query.day,
                query.period,
                query.holder_id,
                query.from_date,
                query.to_date,
            )
        )
