"""Change a waiting expense; it waits for review again."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.pettycash import PettyCashLine, PettyCashSaved, PettyCashUpdate
from ..caller import Caller
from ..ports import Clock
from ..repositories import PettyCashRepository


@dataclass(frozen=True, slots=True)
class UpdatePettyCashEntryCommand:
    caller: Caller
    entry_id: UUID
    line: PettyCashLine
    version: int | None


class UpdatePettyCashEntry:
    def __init__(self, pettycash: PettyCashRepository, clock: Clock) -> None:
        self._pettycash = pettycash
        self._clock = clock

    async def execute(self, command: UpdatePettyCashEntryCommand) -> PettyCashSaved:
        return await self._pettycash.update(
            PettyCashUpdate(
                command.caller.context(self._clock),
                command.entry_id,
                command.line,
                command.version,
            )
        )
