"""Trust a new device with its emailed code (``POST /auth/verify-device``). The third wrong
code voids it; the routine then issues a replacement, mailed after the uniform refusal."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.identity import AuthEnvelope, CodePurpose, DeviceVerification
from ..ports import Clock, CodeHasher, SecretSource, TokenIssuer
from ..repositories import IdentityRepository
from .common import CodeDelivery, answer, phone_argument


@dataclass(frozen=True, slots=True)
class VerifyDeviceCommand:
    request_id: str
    phone_number: str = field(repr=False)
    code: str = field(repr=False)
    device_id: str


class VerifyDevice:
    def __init__(
        self,
        identity: IdentityRepository,
        clock: Clock,
        digests: CodeHasher,
        secrets: SecretSource,
        tokens: TokenIssuer,
        *,
        delivery: CodeDelivery,
        trust_days: int | None,
    ) -> None:
        self._identity = identity
        self._clock = clock
        self._digests = digests
        self._secrets = secrets
        self._tokens = tokens
        self._delivery = delivery
        self._trust_days = trust_days

    async def execute(self, command: VerifyDeviceCommand) -> AuthEnvelope:
        now = self._clock.now()
        replacement = self._secrets.verification_code()
        refresh_token = self._secrets.refresh_token()
        outcome = await self._identity.verify_device(
            DeviceVerification(
                request_id=command.request_id,
                phone=phone_argument(command.phone_number),
                device_id=command.device_id,
                code_hash=self._digests.digest(command.code),
                replacement_code_hash=self._digests.digest(replacement),
                refresh_token_hash=self._digests.digest(refresh_token),
                trust_days=self._trust_days,
                now=now,
            )
        )
        self._delivery.later(
            outcome,
            code=replacement,
            purpose=CodePurpose.NEW_DEVICE,
            device_name=None,
            request_id=command.request_id,
        )
        return answer(
            outcome,
            device_id=command.device_id,
            refresh_token=refresh_token,
            tokens=self._tokens,
            now=now,
        )
