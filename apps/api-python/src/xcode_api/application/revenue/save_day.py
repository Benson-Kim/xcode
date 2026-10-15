"""Save one day for many vehicles, all or nothing, each row as a single capture."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...domain.revenue import RevenueDayResult, RevenueDayRow, RevenueDaySave
from ..caller import Caller
from ..ports import Clock
from ..repositories import RevenueRepository


@dataclass(frozen=True, slots=True)
class SaveRevenueDayCommand:
    caller: Caller
    day: date
    rows: tuple[RevenueDayRow, ...]


class SaveRevenueDay:
    def __init__(self, revenue: RevenueRepository, clock: Clock) -> None:
        self._revenue = revenue
        self._clock = clock

    async def execute(self, command: SaveRevenueDayCommand) -> RevenueDayResult:
        return await self._revenue.save_day(
            RevenueDaySave(command.caller.context(self._clock), command.day, command.rows)
        )
