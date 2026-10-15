"""A report as a file: the routine reads the rows and writes the audit row in one transaction
and answers the document; the writer for its content type then builds the file off the loop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.reports import ExportFile, ExportFormat, ReportExportQuery
from ..caller import Caller
from ..ports import Clock, ReportFileWriter
from ..repositories import ReportsRepository
from .files import build_file


@dataclass(frozen=True, slots=True)
class ExportReportQuery:
    caller: Caller
    group: str
    report: str
    from_date: date | None
    to_date: date | None
    company_id: UUID | None
    holder_id: UUID | None
    q: str | None
    format: str | None


class ExportReport:
    def __init__(
        self,
        reports: ReportsRepository,
        writers: Mapping[ExportFormat, ReportFileWriter],
        clock: Clock,
    ) -> None:
        self._reports = reports
        self._writers = writers
        self._clock = clock

    async def execute(self, query: ExportReportQuery) -> ExportFile:
        document = await self._reports.export_report(
            ReportExportQuery(
                query.caller.context(self._clock),
                query.group,
                query.report,
                query.from_date,
                query.to_date,
                query.company_id,
                query.holder_id,
                query.q,
                query.format,
            )
        )
        return await build_file(self._writers, document)
