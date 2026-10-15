"""The permission catalogue, for any member."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import PermissionGroup
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class GetAccessCatalogQuery:
    caller: Caller


class GetAccessCatalog:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, query: GetAccessCatalogQuery) -> tuple[PermissionGroup, ...]:
        return await self._tenancy.access_catalog(query.caller.context(self._clock))
