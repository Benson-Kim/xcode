"""Sign-in notices after commit: the durable outbox of the emails that tell a person their sign-in
email or mobile number was changed.

``tenancy.save_person`` writes the pending notices with the change: to the replaced and the new
email, or to the current one when only the number changed. :meth:`SignInNotices.send_for` claims
and queues them right after the change commits and records ``sent`` or the failure; a lost
process or a failed send leaves the notice pending, and :meth:`SignInNotices.sweep` sends it
again."""

from __future__ import annotations

import logging
from uuid import UUID

from ...domain.tenancy import PendingSignInNotice, TenantContext
from ..ports import Clock, SignInNotice, SignInNotifier
from ..repositories import TenancyRepository

log = logging.getLogger(__name__)

# One change writes at most two notices; the rest are earlier ones a lost process left unsent.
SEND_LIMIT = 10


class SignInNotices:
    def __init__(self, tenancy: TenancyRepository, clock: Clock, notifier: SignInNotifier) -> None:
        self._tenancy = tenancy
        self._clock = clock
        self._notifier = notifier

    async def send_for(self, context: TenantContext, user_id: UUID) -> int:
        """Queue the notices a change of this person's sign-in details just wrote. A failure to
        claim is logged and left to the sweep: the change is already saved."""
        try:
            claimed = await self._tenancy.claim_sign_in_notices(
                self._clock.now(), SEND_LIMIT, context=context, user_id=user_id
            )
        except Exception:
            log.exception("sign_in_notice.claim_failed")
            return 0
        self._queue_all(claimed)
        return len(claimed)

    async def sweep(self, limit: int) -> int:
        """Send again up to ``limit`` notices whose send was lost or failed. Two instances may
        sweep at once: the claim skips locked rows."""
        claimed = await self._tenancy.claim_sign_in_notices(self._clock.now(), limit)
        self._queue_all(claimed)
        return len(claimed)

    def _queue_all(self, claimed: list[PendingSignInNotice]) -> None:
        for pending in claimed:
            notice = SignInNotice(
                to=pending.address,
                kind=pending.kind,
                first_name=pending.first_name,
                actor_name=pending.actor_name,
                organization_name=pending.organization_name,
                new_address_hint=pending.new_address_hint,
            )
            self._queue(pending.notice_id, notice)

    def _queue(self, notice_id: UUID, notice: SignInNotice) -> None:
        async def sent() -> None:
            await self._tenancy.record_sign_in_notice(notice_id, True, self._clock.now())

        async def failed() -> None:
            await self._tenancy.record_sign_in_notice(notice_id, False, self._clock.now())

        self._notifier.notify(notice, on_sent=sent, on_failure=failed)
