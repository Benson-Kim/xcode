"""The change-log row of the Revenue Summary image. The device draws the picture from the week
on screen; the server only records the export, as it does for every Excel and PDF file."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.reports import RevenueImageLog
from ..caller import Caller
from ..ports import Clock
from ..repositories import ReportsRepository


@dataclass(frozen=True, slots=True)
class LogRevenueSummaryImageCommand:
    caller: Caller
    week_start: date
    company_id: UUID | None
    q: str | None


class LogRevenueSummaryImage:
    def __init__(self, reports: ReportsRepository, clock: Clock) -> None:
        self._reports = reports
        self._clock = clock

    async def execute(self, command: LogRevenueSummaryImageCommand) -> None:
        await self._reports.log_revenue_image(
            RevenueImageLog(
                command.caller.context(self._clock),
                command.week_start,
                command.company_id,
                command.q,
            )
        )
