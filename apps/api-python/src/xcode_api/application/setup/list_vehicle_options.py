"""The vehicles a scheduled item's share can be put on."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.setup import ShareVehicle
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class ListVehicleOptionsQuery:
    caller: Caller


class ListVehicleOptions:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: ListVehicleOptionsQuery) -> tuple[ShareVehicle, ...]:
        return await self._setup.vehicle_options(query.caller.context(self._clock))
