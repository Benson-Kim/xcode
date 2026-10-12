"""The caller's own companies and vehicles."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import MyScope
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class GetMyScopeQuery:
    caller: Caller


class GetMyScope:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, query: GetMyScopeQuery) -> MyScope:
        return await self._tenancy.my_scope(query.caller.context(self._clock))
