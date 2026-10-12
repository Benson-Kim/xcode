"""Store the organization's logo from a data URL and answer the data URL of what was stored.

The data URL is decoded here (its transport encoding: length, shape, base64); the routine
decides the type, size and signature, so the stored bytes are exactly the decoded ones."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import LogoSave, LogoUpload
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class UpdateOrganizationLogoCommand:
    caller: Caller
    data_url: str
    reason: str | None


class UpdateOrganizationLogo:
    def __init__(self, tenancy: TenancyRepository, clock: Clock) -> None:
        self._tenancy = tenancy
        self._clock = clock

    async def execute(self, command: UpdateOrganizationLogoCommand) -> str:
        logo = LogoUpload.parse(command.data_url)
        await self._tenancy.save_logo(
            LogoSave(command.caller.context(self._clock), logo, command.reason)
        )
        return logo.data_url
