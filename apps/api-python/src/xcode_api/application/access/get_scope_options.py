"""The companies and vehicles the caller may hand on as a data scope."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import ScopeOptions
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class GetScopeOptionsQuery:
    caller: Caller


class GetScopeOptions:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, query: GetScopeOptionsQuery) -> ScopeOptions:
        return await self._tenancy.scope_options(query.caller.context(self._clock))
