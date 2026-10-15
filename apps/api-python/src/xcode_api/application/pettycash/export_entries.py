"""The Petty cash screen's entries (the expenses or the cash received) as a file, through the
reports repository and the writer for the format asked."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.reports import ExportFile, ExportFormat, PettyCashExportQuery
from ..caller import Caller
from ..ports import Clock, ReportFileWriter
from ..reports.files import build_file
from ..repositories import ReportsRepository


@dataclass(frozen=True, slots=True)
class ExportPettyCashEntriesQuery:
    caller: Caller
    from_date: date | None
    to_date: date | None
    holder_id: UUID | None
    view: str | None
    statuses: tuple[str, ...] | None
    q: str | None
    format: str | None


class ExportPettyCashEntries:
    def __init__(
        self,
        reports: ReportsRepository,
        writers: Mapping[ExportFormat, ReportFileWriter],
        clock: Clock,
    ) -> None:
        self._reports = reports
        self._writers = writers
        self._clock = clock

    async def execute(self, query: ExportPettyCashEntriesQuery) -> ExportFile:
        document = await self._reports.export_pettycash(
            PettyCashExportQuery(
                query.caller.context(self._clock),
                query.from_date,
                query.to_date,
                query.holder_id,
                query.view,
                query.statuses,
                query.q,
                query.format,
            )
        )
        return await build_file(self._writers, document)
