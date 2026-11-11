"""Deletion notices after commit: the durable outbox of the emails that tell the administrators
who can block members that a member asked to delete their account.

``api.me_deletion_request`` writes one pending notice per recipient with the request, counted as
its first send. :meth:`DeletionNotices.send` queues each after the reply and records ``sent`` or
the failure; a lost process leaves the notice pending, and :meth:`DeletionNotices.sweep` sends it
again, so the 24-hour repeat guard never hides a request no administrator heard of."""

from __future__ import annotations

from uuid import UUID

from ...domain.tenancy import DeletionRequestOutcome
from ..ports import Clock, DeletionNotice, DeletionNotifier
from ..repositories import TenancyRepository


class DeletionNotices:
    def __init__(
        self, tenancy: TenancyRepository, clock: Clock, notifier: DeletionNotifier
    ) -> None:
        self._tenancy = tenancy
        self._clock = clock
        self._notifier = notifier

    def send(self, outcome: DeletionRequestOutcome, organization_id: UUID, request_id: str) -> None:
        for recipient in outcome.recipients:
            self._queue(
                organization_id,
                recipient.notice_id,
                DeletionNotice(
                    to=recipient.email,
                    recipient_first_name=recipient.first_name,
                    requester_name=outcome.requester_name,
                    organization_name=outcome.organization_name,
                    request_id=request_id,
                ),
            )

    async def sweep(self, limit: int) -> int:
        """Send again up to ``limit`` notices whose send was lost or failed. Two instances may
        sweep at once: the claim skips locked rows."""
        claimed = await self._tenancy.claim_deletion_notices(self._clock.now(), limit)
        for pending in claimed:
            self._queue(
                pending.organization_id,
                pending.notice_id,
                DeletionNotice(
                    to=pending.email,
                    recipient_first_name=pending.first_name,
                    requester_name=pending.requester_name,
                    organization_name=pending.organization_name,
                ),
            )
        return len(claimed)

    def _queue(self, organization_id: UUID, notice_id: UUID, notice: DeletionNotice) -> None:
        async def sent() -> None:
            await self._tenancy.record_deletion_notice(
                organization_id, notice_id, True, self._clock.now()
            )

        async def failed() -> None:
            await self._tenancy.record_deletion_notice(
                organization_id, notice_id, False, self._clock.now()
            )

        self._notifier.notify(notice, on_sent=sent, on_failure=failed)
