"""What went into a vehicle and how much of it has come back."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import InvestmentSummary, VehicleQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class GetInvestmentQuery:
    caller: Caller
    vehicle_id: UUID


class GetInvestment:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: GetInvestmentQuery) -> InvestmentSummary:
        return await self._setup.get_investment(
            VehicleQuery(query.caller.context(self._clock), query.vehicle_id)
        )
