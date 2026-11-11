"""The invitation link step (``POST /auth/invite/redeem``): with the link's token and the
person's number, the server stores a fresh first-setup code for this device and answers it
once, so the client goes straight to choosing a PIN. Every mismatch refuses alike."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.identity import AuthEnvelope, AuthOutcomeKind
from ...domain.invitations import InvitationRedeem, InviteProblem, invite_problem
from ...domain.policies import step_envelope_for
from ..observability import report_invitation
from ..ports import Clock, CodeHasher, DeviceTokens, SecretSource
from ..repositories import IdentityRepository
from .common import phone_argument


@dataclass(frozen=True, slots=True)
class RedeemInvitationCommand:
    request_id: str
    token: str = field(repr=False)
    phone_number: str = field(repr=False)
    device_id: str


@dataclass(frozen=True, slots=True)
class InvitationRedeemed:
    """The step envelope, the first-setup code when one was stored (returned once, never
    logged), and the problem a refusal may tell."""

    envelope: AuthEnvelope
    code: str | None = field(default=None, repr=False)
    problem: InviteProblem | None = None


class RedeemInvitation:
    def __init__(
        self,
        identity: IdentityRepository,
        clock: Clock,
        *,
        digests: CodeHasher,
        secrets: SecretSource,
        device_tokens: DeviceTokens,
    ) -> None:
        self._identity = identity
        self._clock = clock
        self._digests = digests
        self._secrets = secrets
        self._device_tokens = device_tokens

    def token_key(self, token: str) -> str:
        """The link token's digest, the only form of it a throttle key may carry."""
        return self._device_tokens.digest(token)

    async def execute(self, command: RedeemInvitationCommand) -> InvitationRedeemed:
        code = self._secrets.verification_code()
        outcome = await self._identity.invite_redeem(
            InvitationRedeem(
                request_id=command.request_id,
                token_hash=self.token_key(command.token),
                phone=phone_argument(command.phone_number),
                device_id=command.device_id,
                code_hash=self._digests.digest(code),
                now=self._clock.now(),
            )
        )
        envelope = step_envelope_for(outcome)
        if outcome.outcome is AuthOutcomeKind.VERIFICATION_REQUIRED and outcome.code_id is not None:
            report_invitation("redeemed")
            return InvitationRedeemed(envelope, code=code)
        return InvitationRedeemed(envelope, problem=invite_problem(outcome.refusal))
