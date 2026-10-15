"""Sign this device out (``POST /auth/sign-out``); always ``signed_out``."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.identity import AuthEnvelope, TokenSignOut
from ...domain.policies import envelope_for
from ..ports import Clock, CodeHasher
from ..repositories import IdentityRepository


@dataclass(frozen=True, slots=True)
class SignOutCommand:
    request_id: str
    refresh_token: str = field(repr=False)
    device_id: str


class SignOut:
    def __init__(self, identity: IdentityRepository, clock: Clock, digests: CodeHasher) -> None:
        self._identity = identity
        self._clock = clock
        self._digests = digests

    async def execute(self, command: SignOutCommand) -> AuthEnvelope:
        outcome = await self._identity.sign_out(
            TokenSignOut(
                request_id=command.request_id,
                token_hash=self._digests.digest(command.refresh_token),
                device_id=command.device_id,
                now=self._clock.now(),
            )
        )
        return envelope_for(outcome)
