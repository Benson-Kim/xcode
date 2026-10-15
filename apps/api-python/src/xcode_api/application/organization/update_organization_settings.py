"""Save one settings section; ``value`` arrives under the document keys."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...domain.tenancy import SettingsSave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class UpdateOrganizationSettingsCommand:
    caller: Caller
    section: str
    value: Any
    reason: str | None


class UpdateOrganizationSettings:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: UpdateOrganizationSettingsCommand) -> WriteResult:
        return await self._tenancy.save_settings(
            SettingsSave(
                command.caller.context(self._clock),
                command.section,
                command.value,
                command.reason,
                None,
            )
        )
