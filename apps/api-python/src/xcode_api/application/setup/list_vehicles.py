"""One page of the vehicles the caller may see, of one company when asked."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import VehicleListQuery, VehiclePage
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class ListVehiclesQuery:
    caller: Caller
    company_id: UUID | None
    page: int
    page_size: int


class ListVehicles:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: ListVehiclesQuery) -> VehiclePage:
        return await self._setup.list_vehicles(
            VehicleListQuery(
                query.caller.context(self._clock), query.company_id, query.page, query.page_size
            )
        )
