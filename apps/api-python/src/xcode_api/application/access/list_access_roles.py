"""The organization's roles with their default permissions."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import AccessRole
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class ListAccessRolesQuery:
    caller: Caller


class ListAccessRoles:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, query: ListAccessRolesQuery) -> tuple[AccessRole, ...]:
        return await self._tenancy.access_roles(query.caller.context(self._clock))
