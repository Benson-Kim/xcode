"""Replace the caller's own preferences."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import PreferenceChoices, PreferencesSave, UserPreferences
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class UpdatePreferencesCommand:
    caller: Caller
    choices: PreferenceChoices


class UpdatePreferences:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: UpdatePreferencesCommand) -> UserPreferences:
        return await self._tenancy.save_preferences(
            PreferencesSave(command.caller.context(self._clock), command.choices)
        )
