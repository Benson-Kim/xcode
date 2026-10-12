"""Check a first-PIN or PIN-reset code without using it up (``POST /auth/setup-pin/verify``,
``POST /auth/pin-reset/verify``). The third wrong code voids it; the routine then issues a
replacement, mailed after the uniform refusal."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.identity import AuthEnvelope, CodeCheck, CodePurpose
from ...domain.policies import envelope_for
from ..ports import Clock, CodeHasher, SecretSource
from ..repositories import IdentityRepository
from .common import CodeDelivery, phone_argument


@dataclass(frozen=True, slots=True)
class VerifyCodeCommand:
    request_id: str
    phone_number: str = field(repr=False)
    code: str = field(repr=False)
    device_id: str
    purpose: CodePurpose


class VerifyCode:
    def __init__(
        self,
        identity: IdentityRepository,
        clock: Clock,
        digests: CodeHasher,
        secrets: SecretSource,
        delivery: CodeDelivery,
    ) -> None:
        self._identity = identity
        self._clock = clock
        self._digests = digests
        self._secrets = secrets
        self._delivery = delivery

    async def execute(self, command: VerifyCodeCommand) -> AuthEnvelope:
        replacement = self._secrets.verification_code()
        outcome = await self._identity.verify_code(
            CodeCheck(
                request_id=command.request_id,
                phone=phone_argument(command.phone_number),
                device_id=command.device_id,
                purpose=command.purpose,
                code_hash=self._digests.digest(command.code),
                replacement_code_hash=self._digests.digest(replacement),
                now=self._clock.now(),
            )
        )
        self._delivery.later(
            outcome,
            code=replacement,
            purpose=command.purpose,
            device_name=None,
            request_id=command.request_id,
        )
        return envelope_for(outcome)
