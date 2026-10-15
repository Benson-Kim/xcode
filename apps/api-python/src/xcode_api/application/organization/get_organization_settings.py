"""The organization settings screen."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import OrganizationSettings
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class GetOrganizationSettingsQuery:
    caller: Caller


class GetOrganizationSettings:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, query: GetOrganizationSettingsQuery) -> OrganizationSettings:
        return await self._tenancy.organization_settings(query.caller.context(self._clock))
