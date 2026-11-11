"""Send a person a new invitation ("Send again"): the routine replaces the live one and logs
the change; the new link and code are mailed after that commit."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import PersonInvite
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository
from .invitation_delivery import InvitationDelivery, InvitationSecrets


@dataclass(frozen=True, slots=True)
class InvitePersonCommand:
    caller: Caller
    user_id: UUID


class InvitePerson:
    def __init__(
        self,
        tenancy: TenancyRepository,
        clock: Clock,
        secrets: InvitationSecrets,
        delivery: InvitationDelivery,
    ) -> None:
        self._tenancy = tenancy
        self._clock = clock
        self._secrets = secrets
        self._delivery = delivery

    async def execute(self, command: InvitePersonCommand) -> WriteResult:
        pair = self._secrets.new()
        context = command.caller.context(self._clock)
        result = await self._tenancy.invite_person(
            PersonInvite(context, command.user_id, pair.hashes)
        )
        await self._delivery.send(pair, request_id=context.request_id)
        return result
