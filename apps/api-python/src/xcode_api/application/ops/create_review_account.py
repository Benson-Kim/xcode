"""Create or renew the App Review login of the demo organization (``docs/08-operability.md``
section 8). Its PIN and its fixed new-device code are drawn here, hashed as every PIN and
code is, and returned once for the operator to hand to App Review; a second run replaces
both. The routine works only in the organization flagged as demo, creating it with made-up
data beside the real one when there is none, so the login never reaches real data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ...domain.identity import CreatedReviewAccount, ReviewAccountCreation
from ...domain.policies import new_pin_problem
from ..ports import Clock, CodeHasher, PinHasher, SecretSource
from ..repositories import OpsRepository

PIN_DRAWS = 100


@dataclass(frozen=True, slots=True)
class CreateReviewAccountCommand:
    operator: str
    request_id: str
    email: str = field(repr=False)
    phone: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ReviewAccount:
    """The login and the two secrets App Review signs in with, shown to the operator once."""

    account: CreatedReviewAccount
    pin: str = field(repr=False)
    code: str = field(repr=False)


class CreateReviewAccount:
    def __init__(
        self,
        ops: OpsRepository,
        clock: Clock,
        *,
        pins: PinHasher,
        codes: CodeHasher,
        secret_source: SecretSource,
        new_pin: Callable[[], str],
    ) -> None:
        self._ops = ops
        self._clock = clock
        self._pins = pins
        self._codes = codes
        self._secret_source = secret_source
        self._new_pin = new_pin

    async def execute(self, command: CreateReviewAccountCommand) -> ReviewAccount:
        pin = self._draw_pin(command.phone)
        code = self._secret_source.verification_code()
        account = await self._ops.create_review_account(
            ReviewAccountCreation(
                operator=command.operator,
                request_id=command.request_id,
                email=command.email,
                phone=command.phone,
                pin_hash=await self._pins.hash(pin),
                code_hash=self._codes.digest(code),
                now=self._clock.now(),
            )
        )
        return ReviewAccount(account=account, pin=pin, code=code)

    def _draw_pin(self, phone: str) -> str:
        for _ in range(PIN_DRAWS):
            pin = self._new_pin()
            if new_pin_problem(pin, phone) is None:
                return pin
        raise RuntimeError(f"no acceptable PIN in {PIN_DRAWS} draws")
