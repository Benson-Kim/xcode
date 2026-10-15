"""Add a PSV company."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.setup import CompanySave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class CreateCompanyCommand:
    caller: Caller
    name: str | None
    reason: str | None


class CreateCompany:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: CreateCompanyCommand) -> WriteResult:
        return await self._setup.create_company(
            CompanySave(command.caller.context(self._clock), None, command.name, command.reason)
        )
