"""Delete a person nothing refers to; the routine decides who may be deleted and refuses one
who has records."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import PersonRemoval
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class DeletePersonCommand:
    caller: Caller
    user_id: UUID


class DeletePerson:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: DeletePersonCommand) -> WriteResult:
        return await self._tenancy.delete_person(
            PersonRemoval(command.caller.context(self._clock), command.user_id)
        )
