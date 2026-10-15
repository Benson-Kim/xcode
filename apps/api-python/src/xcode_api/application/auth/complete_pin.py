"""Set the first PIN or a reset PIN with a valid code (``POST /auth/setup-pin/complete``,
``POST /auth/pin-reset/complete`` and ``POST /auth/pin/new``).

The PIN rules are checked before anything else, with the number the request carries, so a
refused PIN reveals nothing about the number. On a reset the new PIN is also verified against
the stored hash (one more derivation, against the dummy hash when there is none), and the
routine refuses the PIN being replaced only to a request with a valid code. The released
routes answer every refused PIN with ``minimumPinLength`` 4 and trust the device by its id;
``POST /auth/pin/new`` names the problem and trusts the device with a token unless asked not
to.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...domain.identity import (
    AccountLookup,
    AuthEnvelope,
    CodePurpose,
    PinCompletion,
    UserStatus,
)
from ...domain.policies import (
    envelope_for,
    invalid_pin_answer,
    invalid_pin_step,
    new_pin_problem,
    step_envelope_for,
)
from ..ports import Clock, CodeHasher, DeviceTokens, PinHasher, SecretSource, TokenIssuer
from ..repositories import IdentityRepository
from .common import phone_argument, signed
from .sign_in import verify_pin


@dataclass(frozen=True, slots=True)
class CompletePinCommand:
    request_id: str
    phone_number: str = field(repr=False)
    pin: str = field(repr=False)
    code: str = field(repr=False)
    device_id: str
    purpose: CodePurpose
    device_name: str | None = None
    trust: bool = True
    step: bool = False


class CompletePin:
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
        trust_days: int | None,
    ) -> None:
        self._identity = identity
        self._clock = clock
        self._pins = pins
        self._digests = digests
        self._secrets = secrets
        self._device_tokens = device_tokens
        self._tokens = tokens
        self._trust_days = trust_days

    async def execute(self, command: CompletePinCommand) -> AuthEnvelope:
        problem = new_pin_problem(command.pin, command.phone_number)
        if problem is not None:
            return invalid_pin_step(problem) if command.step else invalid_pin_answer()
        now = self._clock.now()
        phone = phone_argument(command.phone_number)
        is_current = False
        checked: str | None = None
        if command.purpose is CodePurpose.PIN_RESET:
            state = await self._identity.account_lookup(
                AccountLookup(command.request_id, phone, command.device_id, now, pin_try=False)
            )
            if state is not None and state.status is UserStatus.ACTIVE:
                checked = state.pin_hash
            is_current = await verify_pin(self._pins, command.pin, checked)
        pin_hash = await self._pins.hash(command.pin)
        refresh_token = self._secrets.refresh_token()
        trust = command.trust or not command.step
        device_token = self._device_tokens.new() if command.step and trust else None
        outcome = await self._identity.complete_pin(
            PinCompletion(
                request_id=command.request_id,
                phone=phone,
                device_id=command.device_id,
                purpose=command.purpose,
                code_hash=self._digests.digest(command.code),
                new_pin_is_current=is_current,
                checked_pin_hash=checked,
                pin_hash=pin_hash,
                device_name=command.device_name,
                trust=trust,
                device_token_hash=None
                if device_token is None
                else self._device_tokens.digest(device_token),
                refresh_token_hash=self._digests.digest(refresh_token),
                trust_days=self._trust_days,
                now=now,
            )
        )
        envelope = step_envelope_for(outcome) if command.step else envelope_for(outcome)
        envelope = signed(
            envelope,
            outcome,
            device_id=command.device_id,
            refresh_token=refresh_token,
            tokens=self._tokens,
            now=now,
        )
        if command.step and outcome.device_token_issued:
            envelope = replace(envelope, device_token=device_token)
        return envelope
