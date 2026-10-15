"""One page of the scheduled expenses and savings the caller may see, filtered by kind,
company and status."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import RecurringListQuery, RecurringPage
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class ListRecurringQuery:
    caller: Caller
    kind: str | None
    company_id: UUID | None
    status: str | None
    page: int
    page_size: int


class ListRecurring:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: ListRecurringQuery) -> RecurringPage:
        return await self._setup.list_recurring(
            RecurringListQuery(
                query.caller.context(self._clock),
                query.kind,
                query.company_id,
                query.status,
                query.page,
                query.page_size,
            )
        )
