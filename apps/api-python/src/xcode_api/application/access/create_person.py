"""Add a person; the routine applies the people rules, answers the new user id and invites
the person in the same transaction. The invitation is mailed after that commit."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import PersonDetails, PersonSave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository
from .invitation_delivery import InvitationDelivery, InvitationSecrets


@dataclass(frozen=True, slots=True)
class CreatePersonCommand:
    caller: Caller
    details: PersonDetails


class CreatePerson:
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

    async def execute(self, command: CreatePersonCommand) -> WriteResult:
        pair = self._secrets.new()
        context = command.caller.context(self._clock)
        result = await self._tenancy.create_person(
            PersonSave(context, None, command.details, None, pair.hashes)
        )
        await self._delivery.send(pair, request_id=context.request_id)
        return result
