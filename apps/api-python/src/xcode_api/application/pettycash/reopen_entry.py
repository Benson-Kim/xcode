"""Reopen an approved or rejected expense with a reason; it waits again."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.pettycash import PettyCashDecision, PettyCashSaved
from ..caller import Caller
from ..ports import Clock
from ..repositories import PettyCashRepository


@dataclass(frozen=True, slots=True)
class ReopenPettyCashEntryCommand:
    caller: Caller
    entry_id: UUID
    version: int | None
    reason: str | None


class ReopenPettyCashEntry:
    def __init__(self, pettycash: PettyCashRepository, clock: Clock) -> None:
        self._pettycash = pettycash
        self._clock = clock

    async def execute(self, command: ReopenPettyCashEntryCommand) -> PettyCashSaved:
        return await self._pettycash.reopen(
            PettyCashDecision(
                command.caller.context(self._clock),
                command.entry_id,
                command.version,
                command.reason,
            )
        )
