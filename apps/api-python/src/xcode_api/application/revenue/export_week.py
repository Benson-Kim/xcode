"""The Revenue screen's week as a file, through the reports repository and the writer for the
format asked."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.reports import ExportFile, ExportFormat, RevenueExportQuery
from ..caller import Caller
from ..ports import Clock, ReportFileWriter
from ..reports.files import build_file
from ..repositories import ReportsRepository


@dataclass(frozen=True, slots=True)
class ExportRevenueWeekQuery:
    caller: Caller
    week_start: date | None
    company_id: UUID | None
    format: str | None


class ExportRevenueWeek:
    def __init__(
        self,
        reports: ReportsRepository,
        writers: Mapping[ExportFormat, ReportFileWriter],
        clock: Clock,
    ) -> None:
        self._reports = reports
        self._writers = writers
        self._clock = clock

    async def execute(self, query: ExportRevenueWeekQuery) -> ExportFile:
        document = await self._reports.export_revenue(
            RevenueExportQuery(
                query.caller.context(self._clock), query.week_start, query.company_id, query.format
            )
        )
        return await build_file(self._writers, document)
