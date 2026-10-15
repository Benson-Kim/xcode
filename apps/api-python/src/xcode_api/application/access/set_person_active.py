"""Activate or deactivate a person; the optional body supplies the version and
the reason, and a missing version is the routine's conflict."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import PersonLifecycle
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class SetPersonActiveCommand:
    caller: Caller
    user_id: UUID
    active: bool
    expected_version: int | None
    reason: str | None


class SetPersonActive:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: SetPersonActiveCommand) -> WriteResult:
        return await self._tenancy.set_person_active(
            PersonLifecycle(
                command.caller.context(self._clock),
                command.user_id,
                command.active,
                command.expected_version,
                command.reason,
            )
        )
