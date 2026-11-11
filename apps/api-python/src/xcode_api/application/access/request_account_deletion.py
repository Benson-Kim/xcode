"""Record the caller's own account-deletion request, then tell the administrators who can block
members after that commit. A repeat within 24 hours records nothing and tells no one; the
reply is the same either way, so it never reveals whether a request was already made."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.tenancy import AccountDeletionRequest, DeletionRequestOutcome
from ..caller import Caller
from ..ports import Clock, DeletionNotice, DeletionNotifier
from ..repositories import TenancyRepository


@dataclass(frozen=True, slots=True)
class RequestAccountDeletionCommand:
    caller: Caller


class RequestAccountDeletion:
    def __init__(
        self, tenancy: TenancyRepository, clock: Clock, notifier: DeletionNotifier
    ) -> None:
        self._tenancy = tenancy
        self._clock = clock
        self._notifier = notifier

    async def execute(self, command: RequestAccountDeletionCommand) -> None:
        context = command.caller.context(self._clock)
        outcome = await self._tenancy.request_account_deletion(AccountDeletionRequest(context))
        if outcome.recorded:
            self._notify(outcome, context.request_id)

    def _notify(self, outcome: DeletionRequestOutcome, request_id: str) -> None:
        for recipient in outcome.recipients:
            self._notifier.notify(
                DeletionNotice(
                    to=recipient.email,
                    recipient_first_name=recipient.first_name,
                    requester_name=outcome.requester_name,
                    organization_name=outcome.organization_name,
                    request_id=request_id,
                )
            )
