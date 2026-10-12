"""What several auth use cases share: the number the routines receive, the token pair that
ends every successful sign-in, and the delivery of the codes a routine issued."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from ...domain.identity import (
    AccessGrant,
    AuthEnvelope,
    AuthOutcome,
    AuthOutcomeKind,
    CodePurpose,
    CodeWithdrawal,
)
from ...domain.policies import envelope_for
from ...domain.values import PhoneNumber
from ..errors import IntegrityBug
from ..ports import Clock, CodeMailer, TokenIssuer, VerificationMail
from ..repositories import IdentityRepository


def phone_argument(text: str) -> str:
    """The normalised number when it parses; otherwise the input as typed, which the routine
    records and refuses like an unknown number."""
    phone = PhoneNumber.parse(text)
    return phone.value if phone is not None else text


def answer(
    outcome: AuthOutcome,
    *,
    device_id: str,
    refresh_token: str,
    tokens: TokenIssuer,
    now: datetime,
) -> AuthEnvelope:
    """The released routes' envelope of an outcome; ``authenticated`` also carries the signed
    access token and the raw refresh token whose digest the routine stored."""
    return signed(
        envelope_for(outcome),
        outcome,
        device_id=device_id,
        refresh_token=refresh_token,
        tokens=tokens,
        now=now,
    )


def signed(
    envelope: AuthEnvelope,
    outcome: AuthOutcome,
    *,
    device_id: str,
    refresh_token: str,
    tokens: TokenIssuer,
    now: datetime,
) -> AuthEnvelope:
    """``envelope`` with the token pair when the outcome is ``authenticated``."""
    if outcome.outcome is not AuthOutcomeKind.AUTHENTICATED:
        return envelope
    access_token = tokens.issue(_grant(outcome, device_id), now=now)
    return replace(envelope, access_token=access_token, refresh_token=refresh_token)


def _grant(outcome: AuthOutcome, device_id: str) -> AccessGrant:
    if (
        outcome.user_id is None
        or outcome.organization_id is None
        or outcome.role is None
        or outcome.security_version is None
        or outcome.access_token_minutes is None
    ):
        raise IntegrityBug("an authenticated outcome lacks its claim material")
    return AccessGrant(
        user_id=outcome.user_id,
        device_id=device_id,
        security_version=outcome.security_version,
        organization_id=outcome.organization_id,
        role=outcome.role,
        first_name=outcome.first_name or "",
        last_name=outcome.last_name or "",
        permissions=outcome.permissions or (),
        lifetime_minutes=outcome.access_token_minutes,
    )


class CodeDelivery:
    """Mails the code a routine issued (the outcome carries its id and the stored address)
    to that address: ``now`` before the reply, withdrawing the code when the send fails;
    ``later`` through the mail queue after the reply, withdrawing it on failure. An outcome
    without an issued code sends nothing."""

    def __init__(self, identity: IdentityRepository, clock: Clock, mail: CodeMailer) -> None:
        self._identity = identity
        self._clock = clock
        self._mail = mail

    async def now(
        self,
        outcome: AuthOutcome,
        *,
        code: str,
        purpose: CodePurpose,
        device_name: str | None,
        request_id: str,
    ) -> bool:
        mail = self._message(outcome, code, purpose, device_name, request_id)
        if mail is None:
            return True
        if await self._mail.send_now(mail):
            return True
        await self._withdraw(request_id, mail.code_id)
        return False

    def later(
        self,
        outcome: AuthOutcome,
        *,
        code: str,
        purpose: CodePurpose,
        device_name: str | None,
        request_id: str,
    ) -> None:
        mail = self._message(outcome, code, purpose, device_name, request_id)
        if mail is None:
            return
        code_id = mail.code_id

        async def withdraw() -> None:
            await self._withdraw(request_id, code_id)

        self._mail.send_later(mail, on_failure=withdraw)

    @staticmethod
    def _message(
        outcome: AuthOutcome,
        code: str,
        purpose: CodePurpose,
        device_name: str | None,
        request_id: str,
    ) -> VerificationMail | None:
        if not outcome.code_issued:
            return None
        if outcome.code_id is None or outcome.email is None:
            raise IntegrityBug("an issued code lacks its id or address")
        return VerificationMail(
            to=outcome.email,
            purpose=purpose,
            code=code,
            code_id=outcome.code_id,
            request_id=request_id,
            device_name=device_name,
        )

    async def _withdraw(self, request_id: str, code_id: UUID) -> None:
        await self._identity.withdraw_code(CodeWithdrawal(request_id, code_id, self._clock.now()))
