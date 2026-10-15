"""What every member's screens need to look and format as chosen."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import Appearance
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class GetAppearanceQuery:
    caller: Caller


class GetAppearance:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, query: GetAppearanceQuery) -> Appearance:
        return await self._tenancy.appearance(query.caller.context(self._clock))
