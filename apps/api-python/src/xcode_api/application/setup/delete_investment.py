"""Remove an investment entry."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import InvestmentRemoval
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class DeleteInvestmentCommand:
    caller: Caller
    entry_id: UUID


class DeleteInvestment:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: DeleteInvestmentCommand) -> WriteResult:
        return await self._setup.delete_investment(
            InvestmentRemoval(command.caller.context(self._clock), command.entry_id)
        )
