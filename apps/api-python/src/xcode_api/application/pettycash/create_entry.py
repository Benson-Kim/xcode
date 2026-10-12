"""Record cash given, an expense or a credit note; the phones replay their offline queue
through the same call with the entry's id."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.pettycash import PettyCashCreate, PettyCashLine, PettyCashSaved
from ..caller import Caller
from ..ports import Clock
from ..repositories import PettyCashRepository


@dataclass(frozen=True, slots=True)
class CreatePettyCashEntryCommand:
    caller: Caller
    id: UUID | None
    line: PettyCashLine


class CreatePettyCashEntry:
    def __init__(self, pettycash: PettyCashRepository, clock: Clock) -> None:
        self._pettycash = pettycash
        self._clock = clock

    async def execute(self, command: CreatePettyCashEntryCommand) -> PettyCashSaved:
        return await self._pettycash.create(
            PettyCashCreate(command.caller.context(self._clock), command.id, command.line)
        )
