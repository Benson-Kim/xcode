"""Make a person reset their PIN at the next sign-in and remove their devices at once."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import PersonPinReset
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class RequirePinResetCommand:
    caller: Caller
    user_id: UUID


class RequirePinReset:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: RequirePinResetCommand) -> WriteResult:
        return await self._tenancy.require_pin_reset(
            PersonPinReset(command.caller.context(self._clock), command.user_id)
        )
