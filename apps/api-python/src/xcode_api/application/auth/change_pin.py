"""Change the PIN from the profile menu (``POST /auth/pin/change``, bearer).

The new PIN's rules are checked with the person's stored number and the current PIN as typed;
one derivation verifies the current PIN (against the dummy hash when there is none), one
hashes the new one, and the routine decides under the account's row lock: a wrong current
PIN counts toward the every-device lock. Sessions and devices stay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from ...domain.identity import AuthEnvelope, PinChange, UserLookup, UserStatus
from ...domain.policies import invalid_pin_step, new_pin_problem, step_envelope_for
from ..ports import Clock, PinHasher
from ..repositories import IdentityRepository
from .sign_in import verify_pin


@dataclass(frozen=True, slots=True)
class ChangePinCommand:
    request_id: str
    user_id: UUID
    device_id: str
    current_pin: str = field(repr=False)
    new_pin: str = field(repr=False)


class ChangePin:
    def __init__(self, identity: IdentityRepository, clock: Clock, *, pins: PinHasher) -> None:
        self._identity = identity
        self._clock = clock
        self._pins = pins

    async def execute(self, command: ChangePinCommand) -> AuthEnvelope:
        now = self._clock.now()
        state = await self._identity.account_lookup_user(
            UserLookup(command.request_id, command.user_id, command.device_id, now)
        )
        problem = new_pin_problem(
            command.new_pin,
            None if state is None else state.phone_number,
            replaced=command.current_pin,
        )
        if problem is not None:
            return invalid_pin_step(problem)
        stored = state.pin_hash if state is not None and state.status is UserStatus.ACTIVE else None
        current_ok = await verify_pin(self._pins, command.current_pin, stored)
        pin_hash = await self._pins.hash(command.new_pin)
        outcome = await self._identity.change_pin(
            PinChange(
                request_id=command.request_id,
                user_id=command.user_id,
                device_id=command.device_id,
                current_ok=current_ok,
                checked_pin_hash=stored,
                pin_hash=pin_hash,
                now=now,
            )
        )
        return step_envelope_for(outcome)
