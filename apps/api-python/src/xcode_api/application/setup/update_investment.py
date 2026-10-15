"""Correct an investment entry."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import InvestmentDetails, InvestmentUpdate
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class UpdateInvestmentCommand:
    caller: Caller
    entry_id: UUID
    details: InvestmentDetails


class UpdateInvestment:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: UpdateInvestmentCommand) -> WriteResult:
        return await self._setup.update_investment(
            InvestmentUpdate(command.caller.context(self._clock), command.entry_id, command.details)
        )
