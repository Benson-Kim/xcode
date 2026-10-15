"""A scheduled item's last runs on the caller's vehicles."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import RecurringRuns, RecurringRunsQuery
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class GetRecurringRunsQuery:
    caller: Caller
    item_id: UUID


class GetRecurringRuns:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: GetRecurringRunsQuery) -> RecurringRuns:
        return await self._setup.recurring_runs(
            RecurringRunsQuery(query.caller.context(self._clock), query.item_id)
        )
