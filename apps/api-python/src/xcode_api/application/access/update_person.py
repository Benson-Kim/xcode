"""Change a person at the version the caller loaded. A new email for a person still without
a PIN re-invites them at the new address (the routine decides); a new email or number is told
to the person at the addresses involved. Both mails go after commit."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.tenancy import PersonDetails, PersonSave
from ...domain.values import WriteOutcome, WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository
from .invitation_delivery import InvitationDelivery, InvitationSecrets
from .sign_in_notices import SignInNotices


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
        notices: SignInNotices,
    ) -> None:
        self._tenancy = tenancy
        self._clock = clock
        self._secrets = secrets
        self._delivery = delivery
        self._notices = notices

    async def execute(self, command: UpdatePersonCommand) -> WriteResult:
        pair = self._secrets.new()
        context = command.caller.context(self._clock)
        result = await self._tenancy.update_person(
            PersonSave(
                context, command.user_id, command.details, command.expected_version, pair.hashes
            )
        )
        await self._delivery.send(pair, request_id=context.request_id)
        if result.outcome is WriteOutcome.UPDATED:
            await self._notices.send_for(context, command.user_id)
        return result
