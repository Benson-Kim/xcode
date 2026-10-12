"""Rename a company."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import CompanySave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class RenameCompanyCommand:
    caller: Caller
    company_id: UUID
    name: str | None
    reason: str | None


class RenameCompany:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: RenameCompanyCommand) -> WriteResult:
        return await self._setup.rename_company(
            CompanySave(
                command.caller.context(self._clock),
                command.company_id,
                command.name,
                command.reason,
            )
        )
