"""Change a person at the version the caller loaded."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import PersonDetails, PersonSave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class UpdatePersonCommand:
    caller: Caller
    user_id: UUID
    details: PersonDetails
    expected_version: int | None


class UpdatePerson:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: UpdatePersonCommand) -> WriteResult:
        return await self._tenancy.update_person(
            PersonSave(
                command.caller.context(self._clock),
                command.user_id,
                command.details,
                command.expected_version,
            )
        )
