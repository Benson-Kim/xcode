"""Switch one system setting on or off for the whole organization."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import SystemSettings, SystemSettingSave
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class SetSystemSettingCommand:
    caller: Caller
    key: str
    on: bool | None


class SetSystemSetting:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: SetSystemSettingCommand) -> SystemSettings:
        return await self._tenancy.set_system_setting(
            SystemSettingSave(command.caller.context(self._clock), command.key, command.on)
        )
