"""Approve the ticked entries, all or none."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.pettycash import PettyCashApproved, PettyCashEntriesApproval, PettyCashTicked
from ..caller import Caller
from ..ports import Clock
from ..repositories import PettyCashRepository


@dataclass(frozen=True, slots=True)
class ApprovePettyCashEntriesCommand:
    caller: Caller
    entries: tuple[PettyCashTicked, ...]


class ApprovePettyCashEntries:
    def __init__(self, pettycash: PettyCashRepository, clock: Clock) -> None:
        self._pettycash = pettycash
        self._clock = clock

    async def execute(self, command: ApprovePettyCashEntriesCommand) -> PettyCashApproved:
        return await self._pettycash.approve_entries(
            PettyCashEntriesApproval(command.caller.context(self._clock), command.entries)
        )
