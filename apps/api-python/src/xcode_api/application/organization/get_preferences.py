"""The caller's own preferences."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import Preferences
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class GetPreferencesQuery:
    caller: Caller


class GetPreferences:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, query: GetPreferencesQuery) -> Preferences:
        return await self._tenancy.preferences(query.caller.context(self._clock))
