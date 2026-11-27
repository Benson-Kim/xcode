"""The organization's on/off system settings for the Settings page."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import SystemSettings
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class GetSystemSettingsQuery:
    caller: Caller


class GetSystemSettings:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, query: GetSystemSettingsQuery) -> SystemSettings:
        return await self._tenancy.system_settings(query.caller.context(self._clock))
