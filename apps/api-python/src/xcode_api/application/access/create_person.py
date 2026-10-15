"""Add a person; the routine applies the people rules and answers the new user id."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import PersonDetails, PersonSave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class CreatePersonCommand:
    caller: Caller
    details: PersonDetails


class CreatePerson:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: CreatePersonCommand) -> WriteResult:
        return await self._tenancy.create_person(
            PersonSave(command.caller.context(self._clock), None, command.details, None)
        )
