"""One page of the people the caller may see."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import PeoplePage, PeopleQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class ListPeopleQuery:
    caller: Caller
    page: int
    page_size: int
    role: str | None = None
    status: str | None = None


class ListPeople:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, query: ListPeopleQuery) -> PeoplePage:
        return await self._tenancy.list_people(
            PeopleQuery(
                query.caller.context(self._clock),
                query.page,
                query.page_size,
                query.role,
                query.status,
            )
        )
