"""What a vehicle brought in and what was set against it over a period or a date range."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.setup import VehicleReport, VehicleReportQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class GetVehicleReportQuery:
    caller: Caller
    vehicle_id: UUID
    period: str | None
    from_date: date | None
    through: date | None


class GetVehicleReport:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: GetVehicleReportQuery) -> VehicleReport:
        return await self._setup.vehicle_report(
            VehicleReportQuery(
                query.caller.context(self._clock),
                query.vehicle_id,
                query.period,
                query.from_date,
                query.through,
            )
        )
