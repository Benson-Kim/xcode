"""The number step (``POST /auth/start``): the server decides what comes after the mobile
number. A code it issues for a first sign-in or a forced reset is mailed after the reply."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...domain.identity import AuthEnvelope, NumberCheck
from ...domain.policies import step_envelope_for
from ..ports import Clock, CodeHasher, DeviceTokens, SecretSource
from ..repositories import IdentityRepository
from .common import CodeDelivery, phone_argument


@dataclass(frozen=True, slots=True)
class StartSignInCommand:
    request_id: str
    phone_number: str = field(repr=False)
    device_id: str
    device_token: str | None = field(repr=False)
    device_name: str | None


class StartSignIn:
    def __init__(
        self,
        identity: IdentityRepository,
        clock: Clock,
        *,
        digests: CodeHasher,
        secrets: SecretSource,
        device_tokens: DeviceTokens,
        delivery: CodeDelivery,
        development_codes: bool,
    ) -> None:
        self._identity = identity
        self._clock = clock
        self._digests = digests
        self._secrets = secrets
        self._device_tokens = device_tokens
        self._delivery = delivery
        self._development_codes = development_codes

    async def execute(self, command: StartSignInCommand) -> AuthEnvelope:
        code = self._secrets.verification_code()
        outcome = await self._identity.start(
            NumberCheck(
                request_id=command.request_id,
                phone=phone_argument(command.phone_number),
                device_id=command.device_id,
                device_token_hash=None
                if command.device_token is None
                else self._device_tokens.digest(command.device_token),
                code_hash=self._digests.digest(code),
                skip_cooldown=self._development_codes,
                now=self._clock.now(),
            )
        )
        if outcome.code_issued and outcome.purpose is not None:
            self._delivery.later(
                outcome,
                code=code,
                purpose=outcome.purpose,
                device_name=command.device_name,
                request_id=command.request_id,
            )
        envelope = step_envelope_for(outcome)
        if self._development_codes and outcome.code_issued:
            return replace(envelope, development_code=code)
        return envelope
