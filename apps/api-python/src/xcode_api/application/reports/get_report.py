"""One page of a fleet or petty-cash report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.reports import ReportQuery, ReportTable
from ..caller import Caller
from ..ports import Clock
from ..repositories import ReportsRepository


@dataclass(frozen=True, slots=True)
class GetReportQuery:
    caller: Caller
    group: str
    report: str
    from_date: date | None
    to_date: date | None
    company_id: UUID | None
    holder_id: UUID | None
    q: str | None
    page: int | None
    page_size: int | None


class GetReport:
    def __init__(self, reports: ReportsRepository, clock: Clock) -> None:
        self._reports = reports
        self._clock = clock

    async def execute(self, query: GetReportQuery) -> ReportTable:
        return await self._reports.report(
            ReportQuery(
                query.caller.context(self._clock),
                query.group,
                query.report,
                query.from_date,
                query.to_date,
                query.company_id,
                query.holder_id,
                query.q,
                query.page,
                query.page_size,
            )
        )
