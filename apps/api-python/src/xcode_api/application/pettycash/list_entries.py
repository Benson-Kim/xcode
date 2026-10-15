"""One page of the petty-cash entries the caller may see."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.pettycash import PettyCashEntryPage, PettyCashEntryQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import PettyCashRepository


@dataclass(frozen=True, slots=True)
class ListPettyCashEntriesQuery:
    caller: Caller
    from_date: date | None
    to_date: date | None
    holder_id: UUID | None
    kinds: tuple[str, ...] | None
    statuses: tuple[str, ...] | None
    q: str | None
    page: int | None
    page_size: int | None


class ListPettyCashEntries:
    def __init__(self, pettycash: PettyCashRepository, clock: Clock) -> None:
        self._pettycash = pettycash
        self._clock = clock

    async def execute(self, query: ListPettyCashEntriesQuery) -> PettyCashEntryPage:
        return await self._pettycash.entries(
            PettyCashEntryQuery(
                query.caller.context(self._clock),
                query.from_date,
                query.to_date,
                query.holder_id,
                query.kinds,
                query.statuses,
                query.q,
                query.page,
                query.page_size,
            )
        )
