"""The Central expenses ledger as a file, through the reports repository and the writer for
the format asked."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from ...domain.reports import ExpenseExportQuery, ExportFile, ExportFormat
from ..caller import Caller
from ..ports import Clock, ReportFileWriter
from ..reports.files import build_file
from ..repositories import ReportsRepository


@dataclass(frozen=True, slots=True)
class ExportExpenseLedgerQuery:
    caller: Caller
    from_date: date | None
    to_date: date | None
    source: str | None
    q: str | None
    format: str | None


class ExportExpenseLedger:
    def __init__(
        self,
        reports: ReportsRepository,
        writers: Mapping[ExportFormat, ReportFileWriter],
        clock: Clock,
    ) -> None:
        self._reports = reports
        self._writers = writers
        self._clock = clock

    async def execute(self, query: ExportExpenseLedgerQuery) -> ExportFile:
        document = await self._reports.export_expenses(
            ExpenseExportQuery(
                query.caller.context(self._clock),
                query.from_date,
                query.to_date,
                query.source,
                query.q,
                query.format,
            )
        )
        return await build_file(self._writers, document)
