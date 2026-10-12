"""The code step (``POST /auth/code``).

A ``new_device`` code that matches signs the device in, trusted with a fresh device token
unless "Trust this device" was unticked; a first-sign-in or reset code that matches answers
``code_verified`` for the new-PIN step. The third wrong code voids it and the routine issues a
replacement, mailed after the reply.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...domain.identity import AuthEnvelope, CodeEntry, CodePurpose
from ...domain.policies import step_envelope_for
from ..ports import Clock, CodeHasher, DeviceTokens, SecretSource, TokenIssuer
from ..repositories import IdentityRepository
from .common import CodeDelivery, phone_argument, signed


@dataclass(frozen=True, slots=True)
class EnterCodeCommand:
    request_id: str
    phone_number: str = field(repr=False)
    device_id: str
    device_name: str | None
    purpose: CodePurpose
    code: str = field(repr=False)
    trust: bool


class EnterCode:
    def __init__(
        self,
        identity: IdentityRepository,
        clock: Clock,
        *,
        digests: CodeHasher,
        secrets: SecretSource,
        device_tokens: DeviceTokens,
        tokens: TokenIssuer,
        delivery: CodeDelivery,
        trust_days: int | None,
    ) -> None:
        self._identity = identity
        self._clock = clock
        self._digests = digests
        self._secrets = secrets
        self._device_tokens = device_tokens
        self._tokens = tokens
        self._delivery = delivery
        self._trust_days = trust_days

    async def execute(self, command: EnterCodeCommand) -> AuthEnvelope:
        now = self._clock.now()
        replacement = self._secrets.verification_code()
        refresh_token = self._secrets.refresh_token()
        device_token = (
            self._device_tokens.new()
            if command.trust and command.purpose is CodePurpose.NEW_DEVICE
            else None
        )
        outcome = await self._identity.check_code(
            CodeEntry(
                request_id=command.request_id,
                phone=phone_argument(command.phone_number),
                device_id=command.device_id,
                purpose=command.purpose,
                code_hash=self._digests.digest(command.code),
                replacement_code_hash=self._digests.digest(replacement),
                device_name=command.device_name,
                trust=command.trust,
                device_token_hash=None
                if device_token is None
                else self._device_tokens.digest(device_token),
                refresh_token_hash=self._digests.digest(refresh_token),
                trust_days=self._trust_days,
                now=now,
            )
        )
        self._delivery.later(
            outcome,
            code=replacement,
            purpose=command.purpose,
            device_name=command.device_name,
            request_id=command.request_id,
        )
        envelope = signed(
            step_envelope_for(outcome),
            outcome,
            device_id=command.device_id,
            refresh_token=refresh_token,
            tokens=self._tokens,
            now=now,
        )
        if outcome.device_token_issued:
            envelope = replace(envelope, device_token=device_token)
        return envelope
