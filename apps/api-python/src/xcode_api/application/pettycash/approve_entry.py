"""Approve one waiting expense."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.pettycash import PettyCashDecision, PettyCashSaved
from ..caller import Caller
from ..ports import Clock
from ..repositories import PettyCashRepository


@dataclass(frozen=True, slots=True)
class ApprovePettyCashEntryCommand:
    caller: Caller
    entry_id: UUID
    version: int | None


class ApprovePettyCashEntry:
    def __init__(self, pettycash: PettyCashRepository, clock: Clock) -> None:
        self._pettycash = pettycash
        self._clock = clock

    async def execute(self, command: ApprovePettyCashEntryCommand) -> PettyCashSaved:
        return await self._pettycash.approve(
            PettyCashDecision(
                command.caller.context(self._clock),
                command.entry_id,
                command.version,
                None,
            )
        )
