"""Bring an archived company back into use."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import CompanyLifecycle
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class RestoreCompanyCommand:
    caller: Caller
    company_id: UUID
    reason: str | None


class RestoreCompany:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: RestoreCompanyCommand) -> WriteResult:
        return await self._setup.restore_company(
            CompanyLifecycle(
                command.caller.context(self._clock), command.company_id, command.reason
            )
        )
