"""The choices of the petty-cash entry form on its date."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...domain.pettycash import PettyCashOptions, PettyCashOptionsQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import PettyCashRepository


@dataclass(frozen=True, slots=True)
class GetPettyCashOptionsQuery:
    caller: Caller
    day: date | None


class GetPettyCashOptions:
    def __init__(self, pettycash: PettyCashRepository, clock: Clock) -> None:
        self._pettycash = pettycash
        self._clock = clock

    async def execute(self, query: GetPettyCashOptionsQuery) -> PettyCashOptions:
        return await self._pettycash.options(
            PettyCashOptionsQuery(query.caller.context(self._clock), query.day)
        )
