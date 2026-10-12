"""Delete an entry (kept, marked removed), with a reason where one is needed."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.pettycash import PettyCashDecision, PettyCashSaved
from ..caller import Caller
from ..ports import Clock
from ..repositories import PettyCashRepository


@dataclass(frozen=True, slots=True)
class RemovePettyCashEntryCommand:
    caller: Caller
    entry_id: UUID
    version: int | None
    reason: str | None


class RemovePettyCashEntry:
    def __init__(self, pettycash: PettyCashRepository, clock: Clock) -> None:
        self._pettycash = pettycash
        self._clock = clock

    async def execute(self, command: RemovePettyCashEntryCommand) -> PettyCashSaved:
        return await self._pettycash.remove(
            PettyCashDecision(
                command.caller.context(self._clock),
                command.entry_id,
                command.version,
                command.reason,
            )
        )
