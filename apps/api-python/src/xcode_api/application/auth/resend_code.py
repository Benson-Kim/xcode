"""The "Send a new code" step (``POST /auth/code/resend``): the answer is the same whether or not a
code was issued, and never carries the masked address; an issued code is mailed after the
reply."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...domain.identity import AuthEnvelope, CodePurpose, CodeResend
from ...domain.policies import step_envelope_for
from ..ports import Clock, CodeHasher, SecretSource
from ..repositories import IdentityRepository
from .common import CodeDelivery, phone_argument


@dataclass(frozen=True, slots=True)
class ResendCodeCommand:
    request_id: str
    phone_number: str = field(repr=False)
    device_id: str
    device_name: str | None
    purpose: CodePurpose


class ResendCode:
    def __init__(
        self,
        identity: IdentityRepository,
        clock: Clock,
        *,
        digests: CodeHasher,
        secrets: SecretSource,
        delivery: CodeDelivery,
        development_codes: bool,
    ) -> None:
        self._identity = identity
        self._clock = clock
        self._digests = digests
        self._secrets = secrets
        self._delivery = delivery
        self._development_codes = development_codes

    async def execute(self, command: ResendCodeCommand) -> AuthEnvelope:
        code = self._secrets.verification_code()
        outcome = await self._identity.resend_code(
            CodeResend(
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
        envelope = replace(step_envelope_for(outcome, masked=False), purpose=command.purpose)
        if self._development_codes and outcome.code_issued:
            return replace(envelope, development_code=code)
        return envelope
