"""The petty-cash dashboard cards."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.pettycash import PettyCashDashboard
from ..caller import Caller
from ..ports import Clock
from ..repositories import PettyCashRepository


@dataclass(frozen=True, slots=True)
class GetPettyCashDashboardQuery:
    caller: Caller


class GetPettyCashDashboard:
    def __init__(self, pettycash: PettyCashRepository, clock: Clock) -> None:
        self._pettycash = pettycash
        self._clock = clock

    async def execute(self, query: GetPettyCashDashboardQuery) -> PettyCashDashboard:
        return await self._pettycash.dashboard(query.caller.context(self._clock))
