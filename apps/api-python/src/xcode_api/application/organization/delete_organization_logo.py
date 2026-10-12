"""Remove the organization's logo."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import LogoRemoval
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class DeleteOrganizationLogoCommand:
    caller: Caller
    reason: str | None


class DeleteOrganizationLogo:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: DeleteOrganizationLogoCommand) -> WriteResult:
        return await self._tenancy.delete_logo(
            LogoRemoval(command.caller.context(self._clock), command.reason)
        )
