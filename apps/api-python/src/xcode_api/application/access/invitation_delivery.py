"""Invitation secrets and their delivery after commit: the durable outbox of invitations.

A use case makes a pair, passes only its digests to the routine that commits the invitation,
then calls :meth:`InvitationDelivery.send`. The routine answers what to mail only while the
invitation is pending with that hash, so a pair the routine did not use sends nothing. The
send runs through the mail queue and records ``sent`` or ``failed``; a lost process leaves
the row pending, and :meth:`InvitationDelivery.sweep` re-issues it under a fresh pair."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ...domain.invitations import InvitationHashes, PendingInvitation
from ..observability import report_invitation
from ..ports import Clock, CodeHasher, DeviceTokens, InvitationMail, InvitationMailer, SecretSource
from ..repositories import InvitationRepository

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InvitationPair:
    """A fresh link token and code with their digests. The raw values are never in ``repr``."""

    token: str = field(repr=False)
    code: str = field(repr=False)
    hashes: InvitationHashes


class InvitationSecrets:
    """Makes invitation pairs: the token is a trusted-device-shaped token (32 random bytes,
    SHA-256 stored) and the code a verification code (keyed digest stored), so the code an
    invitation carries is checked exactly like a mailed one."""

    def __init__(
        self, device_tokens: DeviceTokens, secrets: SecretSource, digests: CodeHasher
    ) -> None:
        self._device_tokens = device_tokens
        self._secrets = secrets
        self._digests = digests

    def new(self) -> InvitationPair:
        token = self._device_tokens.new()
        code = self._secrets.verification_code()
        return InvitationPair(
            token,
            code,
            InvitationHashes(self._device_tokens.digest(token), self._digests.digest(code)),
        )


class InvitationDelivery:
    """Mails invitations after the routine that made them has committed."""

    def __init__(
        self,
        invitations: InvitationRepository,
        clock: Clock,
        mailer: InvitationMailer,
        secrets: InvitationSecrets,
    ) -> None:
        self._invitations = invitations
        self._clock = clock
        self._mailer = mailer
        self._secrets = secrets

    async def send(self, pair: InvitationPair, *, request_id: str | None) -> None:
        """Queue the invitation made with ``pair``, if the routine made one. A failure to start
        is logged and left to the sweep: the person and the invitation are already saved."""
        try:
            pending = await self._invitations.start_delivery(
                pair.hashes.token_hash, self._clock.now()
            )
        except Exception:
            log.exception("invitation.start_failed")
            return
        if pending is not None:
            self._queue(pending, pair, request_id)

    async def sweep(self, limit: int) -> int:
        """Re-issue up to ``limit`` invitations whose send was lost, each under a fresh pair,
        and queue them. Two instances may sweep at once: the claim skips locked rows."""
        pairs = [self._secrets.new() for _ in range(limit)]
        claimed = await self._invitations.claim_undelivered(
            self._clock.now(),
            limit,
            [p.hashes.token_hash for p in pairs],
            [p.hashes.code_hash for p in pairs],
        )
        for pending in claimed:
            if pending.pair_index is None or not 0 <= pending.pair_index < len(pairs):
                log.error("invitation.claim_unpaired invitation_id=%s", pending.invitation_id)
                continue
            self._queue(pending, pairs[pending.pair_index], None)
        return len(claimed)

    def _queue(
        self, pending: PendingInvitation, pair: InvitationPair, request_id: str | None
    ) -> None:
        token_hash = pair.hashes.token_hash

        async def sent() -> None:
            report_invitation("sent")
            await self._invitations.record_delivery(token_hash, True, self._clock.now())

        async def failed() -> None:
            report_invitation("failed")
            await self._invitations.record_delivery(token_hash, False, self._clock.now())

        self._mailer.send_later(
            InvitationMail(
                to=pending.email,
                token=pair.token,
                code=pair.code,
                invitation_id=pending.invitation_id,
                first_name=pending.first_name,
                organization_name=pending.organization_name,
                expires_at=pending.expires_at,
                time_zone=pending.time_zone,
                inviter_name=pending.inviter_name,
                support_email=pending.support_email,
                request_id=request_id,
            ),
            on_sent=sent,
            on_failure=failed,
        )
