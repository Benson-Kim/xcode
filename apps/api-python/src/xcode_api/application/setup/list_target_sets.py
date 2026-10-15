"""A vehicle's target sets, newest first."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import TargetSetSummary, VehicleQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class ListTargetSetsQuery:
    caller: Caller
    vehicle_id: UUID


class ListTargetSets:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: ListTargetSetsQuery) -> tuple[TargetSetSummary, ...]:
        return await self._setup.list_target_sets(
            VehicleQuery(query.caller.context(self._clock), query.vehicle_id)
        )
