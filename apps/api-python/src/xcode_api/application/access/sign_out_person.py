"""Remove every trusted device of a person ("Remove all"), ending their sessions."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import PersonSignOut
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class SignOutPersonCommand:
    caller: Caller
    user_id: UUID


class SignOutPerson:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: SignOutPersonCommand) -> WriteResult:
        return await self._tenancy.sign_out_person(
            PersonSignOut(command.caller.context(self._clock), command.user_id)
        )
