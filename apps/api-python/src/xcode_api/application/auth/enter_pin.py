"""The PIN step (``POST /auth/pin``).

Lookup, exactly one PBKDF2 verification (against the dummy hash when no stored hash may be
used), then the decision routine. A right PIN on a device without a valid token mails a
``new_device`` code before the reply (a failed send withdraws it and answers
``service_unavailable``); a first-sign-in or reset code is mailed after the reply.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...domain.identity import AccountLookup, AuthEnvelope, CodePurpose, PinCheck
from ...domain.policies import needs_dummy_hash, service_unavailable_answer, step_envelope_for
from ..ports import Clock, CodeHasher, DeviceTokens, PinHasher, SecretSource, TokenIssuer
from ..repositories import IdentityRepository
from .common import CodeDelivery, phone_argument, signed
from .sign_in import verify_pin


@dataclass(frozen=True, slots=True)
class EnterPinCommand:
    request_id: str
    phone_number: str = field(repr=False)
    device_id: str
    device_token: str | None = field(repr=False)
    device_name: str | None
    pin: str = field(repr=False)


class EnterPin:
    def __init__(
        self,
        identity: IdentityRepository,
        clock: Clock,
        *,
        pins: PinHasher,
        digests: CodeHasher,
        secrets: SecretSource,
        device_tokens: DeviceTokens,
        tokens: TokenIssuer,
        delivery: CodeDelivery,
        development_codes: bool,
    ) -> None:
        self._identity = identity
        self._clock = clock
        self._pins = pins
        self._digests = digests
        self._secrets = secrets
        self._device_tokens = device_tokens
        self._tokens = tokens
        self._delivery = delivery
        self._development_codes = development_codes

    async def execute(self, command: EnterPinCommand) -> AuthEnvelope:
        now = self._clock.now()
        phone = phone_argument(command.phone_number)
        token_hash = (
            "" if command.device_token is None else self._device_tokens.digest(command.device_token)
        )
        state = await self._identity.account_lookup(
            AccountLookup(command.request_id, phone, command.device_id, now, token_hash)
        )
        stored = None if needs_dummy_hash(state) or state is None else state.pin_hash
        pin_ok = await verify_pin(self._pins, command.pin, stored)
        code = self._secrets.verification_code()
        refresh_token = self._secrets.refresh_token()
        outcome = await self._identity.pin(
            PinCheck(
                request_id=command.request_id,
                phone=phone,
                device_id=command.device_id,
                device_token_hash=token_hash,
                pin_ok=pin_ok,
                checked_pin_hash=stored,
                code_hash=self._digests.digest(code),
                refresh_token_hash=self._digests.digest(refresh_token),
                skip_cooldown=self._development_codes,
                now=now,
            )
        )
        if outcome.code_issued and outcome.purpose is CodePurpose.NEW_DEVICE:
            sent = await self._delivery.now(
                outcome,
                code=code,
                purpose=outcome.purpose,
                device_name=command.device_name,
                request_id=command.request_id,
            )
            if not sent:
                return service_unavailable_answer()
        elif outcome.code_issued and outcome.purpose is not None:
            self._delivery.later(
                outcome,
                code=code,
                purpose=outcome.purpose,
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
        if self._development_codes and outcome.code_issued:
            return replace(envelope, development_code=code)
        return envelope
