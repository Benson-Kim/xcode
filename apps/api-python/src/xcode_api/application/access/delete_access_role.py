"""Delete a custom role nobody holds."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import RoleRemoval
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class DeleteAccessRoleCommand:
    caller: Caller
    role_id: UUID


class DeleteAccessRole:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: DeleteAccessRoleCommand) -> WriteResult:
        return await self._tenancy.delete_access_role(
            RoleRemoval(command.caller.context(self._clock), command.role_id)
        )
