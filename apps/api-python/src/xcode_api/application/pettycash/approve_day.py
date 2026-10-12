"""Approve the waiting expenses of a day, or of the days up to ``to``, that the caller may
approve; the rest are skipped."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ...domain.pettycash import PettyCashApproved, PettyCashDayApproval
from ..caller import Caller
from ..ports import Clock
from ..repositories import PettyCashRepository


@dataclass(frozen=True, slots=True)
class ApprovePettyCashDayCommand:
    caller: Caller
    day: date | None
    to: date | None
    holder_id: UUID | None


class ApprovePettyCashDay:
    def __init__(self, pettycash: PettyCashRepository, clock: Clock) -> None:
        self._pettycash = pettycash
        self._clock = clock

    async def execute(self, command: ApprovePettyCashDayCommand) -> PettyCashApproved:
        return await self._pettycash.approve_day(
            PettyCashDayApproval(
                command.caller.context(self._clock),
                command.day,
                command.to,
                command.holder_id,
            )
        )
