"""Record the caller's own account-deletion request, then tell the administrators who can block
members after that commit, through the notice outbox. A repeat within 24 hours records nothing
and tells no one; the reply is the same either way, so it never reveals whether a request was
already made."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import AccountDeletionRequest
from ..caller import Caller
from ..ports import Clock
from ..repositories import TenancyRepository
from .deletion_notices import DeletionNotices


@dataclass(frozen=True, slots=True)
class RequestAccountDeletionCommand:
    caller: Caller


class RequestAccountDeletion:
    def __init__(self, tenancy: TenancyRepository, clock: Clock, notices: DeletionNotices) -> None:
        self._tenancy = tenancy
        self._clock = clock
        self._notices = notices

    async def execute(self, command: RequestAccountDeletionCommand) -> None:
        context = command.caller.context(self._clock)
        outcome = await self._tenancy.request_account_deletion(AccountDeletionRequest(context))
        if outcome.recorded and context.organization_id is not None:
            self._notices.send(outcome, context.organization_id, context.request_id)
