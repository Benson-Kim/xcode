"""The companies in use that a vehicle can be put in."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.setup import CompanyChoice
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class ListCompanyOptionsQuery:
    caller: Caller


class ListCompanyOptions:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, query: ListCompanyOptionsQuery) -> tuple[CompanyChoice, ...]:
        return await self._setup.company_options(query.caller.context(self._clock))
