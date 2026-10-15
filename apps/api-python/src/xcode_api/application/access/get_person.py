"""One person the caller may see."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import Person, PersonQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class GetPersonQuery:
    caller: Caller
    user_id: UUID


class GetPerson:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, query: GetPersonQuery) -> Person:
        return await self._tenancy.get_person(
            PersonQuery(query.caller.context(self._clock), query.user_id)
        )
