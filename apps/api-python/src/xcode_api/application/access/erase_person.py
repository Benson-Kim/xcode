"""Erase the personal details of a blocked person who asked for their account to be deleted;
the routine decides who may be erased and what is kept."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import PersonErasure
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class ErasePersonCommand:
    caller: Caller
    user_id: UUID
    expected_version: int
    reason: str | None


class ErasePerson:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: ErasePersonCommand) -> WriteResult:
        return await self._tenancy.erase_person(
            PersonErasure(
                command.caller.context(self._clock),
                command.user_id,
                command.expected_version,
                command.reason,
            )
        )
