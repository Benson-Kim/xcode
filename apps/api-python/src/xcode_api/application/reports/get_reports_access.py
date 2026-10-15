"""The reports the caller may open."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.reports import ReportsAccess
from ..caller import Caller
from ..ports import Clock
from ..repositories import ReportsRepository


@dataclass(frozen=True, slots=True)
class GetReportsAccessQuery:
    caller: Caller


class GetReportsAccess:
    def __init__(self, reports: ReportsRepository, clock: Clock) -> None:
        self._reports = reports
        self._clock = clock

    async def execute(self, query: GetReportsAccessQuery) -> ReportsAccess:
        return await self._reports.access(query.caller.context(self._clock))
