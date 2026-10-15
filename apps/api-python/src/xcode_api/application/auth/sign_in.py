"""Sign in with a PIN on the released routes (``POST /auth/sign-in`` and
``POST /auth/unlock``).

Lookup, exactly one PBKDF2 verification (against the dummy hash when no stored hash may be
used), then the decision routine. A right PIN on a new device mails a ``new_device`` code
before the reply; when that mail fails the code is withdrawn and the answer is
``service_unavailable``. The device is trusted by its id alone, as every v2.11 phone is.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...domain.identity import (
    AccountLookup,
    AuthEnvelope,
    AuthOutcomeKind,
    CodePurpose,
    PinVerdict,
)
from ...domain.policies import envelope_for, needs_dummy_hash, service_unavailable_answer
from ..ports import Clock, CodeHasher, PinHasher, SecretSource, TokenIssuer
from ..repositories import IdentityRepository
from .common import CodeDelivery, answer, phone_argument


@dataclass(frozen=True, slots=True)
class SignInCommand:
    request_id: str
    phone_number: str = field(repr=False)
    pin: str = field(repr=False)
    device_id: str


class SignIn:
    def __init__(
        self,
        identity: IdentityRepository,
        clock: Clock,
        *,
        pins: PinHasher,
        digests: CodeHasher,
        secrets: SecretSource,
        tokens: TokenIssuer,
        delivery: CodeDelivery,
        development_codes: bool,
    ) -> None:
        self._identity = identity
        self._clock = clock
        self._pins = pins
        self._digests = digests
        self._secrets = secrets
        self._tokens = tokens
        self._delivery = delivery
        self._development_codes = development_codes

    async def execute(self, command: SignInCommand) -> AuthEnvelope:
        now = self._clock.now()
        state = await self._identity.account_lookup(
            AccountLookup(
                command.request_id, phone_argument(command.phone_number), command.device_id, now
            )
        )
        stored = None if needs_dummy_hash(state) or state is None else state.pin_hash
        pin_ok = await verify_pin(self._pins, command.pin, stored)
        code = self._secrets.verification_code()
        refresh_token = self._secrets.refresh_token()
        outcome = await self._identity.sign_in(
            PinVerdict(
                request_id=command.request_id,
                user_id=None if state is None else state.user_id,
                device_id=command.device_id,
                pin_ok=pin_ok,
                checked_pin_hash=stored,
                code_hash=self._digests.digest(code),
                refresh_token_hash=self._digests.digest(refresh_token),
                skip_cooldown=self._development_codes,
                now=now,
            )
        )
        if outcome.outcome is AuthOutcomeKind.VERIFICATION_REQUIRED and outcome.code_issued:
            sent = await self._delivery.now(
                outcome,
                code=code,
                purpose=CodePurpose.NEW_DEVICE,
                device_name=None,
                request_id=command.request_id,
            )
            if not sent:
                return service_unavailable_answer()
            envelope = envelope_for(outcome)
            return replace(envelope, development_code=code) if self._development_codes else envelope
        return answer(
            outcome,
            device_id=command.device_id,
            refresh_token=refresh_token,
            tokens=self._tokens,
            now=now,
        )


async def verify_pin(pins: PinHasher, pin: str, stored: str | None) -> bool:
    """One derivation always: against the stored hash, or the dummy hash when there is none."""
    if stored is None:
        await pins.dummy_verify(pin)
        return False
    return await pins.verify(pin, stored)
