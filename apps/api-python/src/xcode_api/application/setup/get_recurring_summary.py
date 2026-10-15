"""This month's scheduled costs and savings on the caller's vehicles."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.setup import RecurringMonth
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class GetRecurringSummaryQuery:
    caller: Caller


class GetRecurringSummary:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: GetRecurringSummaryQuery) -> RecurringMonth:
        return await self._setup.recurring_month(query.caller.context(self._clock))
