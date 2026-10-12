"""Record money put into a vehicle."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import InvestmentCreate, InvestmentDetails
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class CreateInvestmentCommand:
    caller: Caller
    vehicle_id: UUID
    details: InvestmentDetails


class CreateInvestment:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: CreateInvestmentCommand) -> WriteResult:
        return await self._setup.create_investment(
            InvestmentCreate(
                command.caller.context(self._clock), command.vehicle_id, command.details
            )
        )
