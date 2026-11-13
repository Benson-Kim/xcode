"""Create a custom role, or change one at the version the caller saw; the routine decides
which names and permissions the caller may give."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import AccessRole, RoleSave
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class SaveAccessRoleCommand:
    caller: Caller
    role_id: UUID | None
    name: str | None
    permissions: tuple[str, ...] | None
    expected_version: int | None = None


class SaveAccessRole:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: SaveAccessRoleCommand) -> AccessRole:
        return await self._tenancy.save_access_role(
            RoleSave(
                command.caller.context(self._clock),
                command.role_id,
                command.name,
                command.permissions,
                command.expected_version,
            )
        )
