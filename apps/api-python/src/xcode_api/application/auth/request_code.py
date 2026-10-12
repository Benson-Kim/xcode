"""Ask for a first-PIN or PIN-reset code (``POST /auth/setup-pin/request``,
``POST /auth/pin-reset/request``, and "Forgot PIN" ``POST /auth/pin/forgot``).

The answer is the same whether or not a code was issued (``check_email`` on the released
routes, ``verification_required`` without the masked address on "Forgot PIN"). An issued code
is mailed after the reply, only once the routine that stored it has returned; when that mail
fails the code is withdrawn.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...domain.identity import AuthEnvelope, AuthOutcome, CodePurpose, CodeRequest
from ...domain.policies import envelope_for, step_envelope_for
from ..ports import Clock, CodeHasher, SecretSource
from ..repositories import IdentityRepository
from .common import CodeDelivery, phone_argument


@dataclass(frozen=True, slots=True)
class RequestCodeCommand:
    request_id: str
    phone_number: str = field(repr=False)
    device_id: str
    purpose: CodePurpose
    device_name: str | None = None
    step: bool = False


class RequestCode:
    def __init__(
        self,
        identity: IdentityRepository,
        clock: Clock,
        digests: CodeHasher,
        secrets: SecretSource,
        delivery: CodeDelivery,
        *,
        development_codes: bool,
    ) -> None:
        self._identity = identity
        self._clock = clock
        self._digests = digests
        self._secrets = secrets
        self._delivery = delivery
        self._development_codes = development_codes

    async def execute(self, command: RequestCodeCommand) -> AuthEnvelope:
        code = self._secrets.verification_code()
        outcome = await self._identity.request_code(
            CodeRequest(
                request_id=command.request_id,
                phone=phone_argument(command.phone_number),
                device_id=command.device_id,
                purpose=command.purpose,
                code_hash=self._digests.digest(code),
                skip_cooldown=self._development_codes,
                now=self._clock.now(),
            )
        )
        self._delivery.later(
            outcome,
            code=code,
            purpose=command.purpose,
            device_name=command.device_name,
            request_id=command.request_id,
        )
        envelope = self._envelope(outcome, command)
        if self._development_codes and outcome.code_issued:
            return replace(envelope, development_code=code)
        return envelope

    @staticmethod
    def _envelope(outcome: AuthOutcome, command: RequestCodeCommand) -> AuthEnvelope:
        if command.step:
            return replace(step_envelope_for(outcome, masked=False), purpose=command.purpose)
        return envelope_for(outcome)
