"""Change a person at the version the caller loaded. A new email for a person still without
a PIN re-invites them at the new address (the routine decides); that mail goes after commit."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import PersonDetails, PersonSave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository
from .invitation_delivery import InvitationDelivery, InvitationSecrets


@dataclass(frozen=True, slots=True)
class UpdatePersonCommand:
    caller: Caller
    user_id: UUID
    details: PersonDetails
    expected_version: int | None


class UpdatePerson:
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

    async def execute(self, command: UpdatePersonCommand) -> WriteResult:
        pair = self._secrets.new()
        context = command.caller.context(self._clock)
        result = await self._tenancy.update_person(
            PersonSave(
                context, command.user_id, command.details, command.expected_version, pair.hashes
            )
        )
        await self._delivery.send(pair, request_id=context.request_id)
        return result
