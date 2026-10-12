"""Rotate a refresh token for a new pair (``POST /auth/refresh``)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.identity import AuthEnvelope, TokenRefresh
from ..ports import Clock, CodeHasher, SecretSource, TokenIssuer
from ..repositories import IdentityRepository
from .common import answer


@dataclass(frozen=True, slots=True)
class RefreshCommand:
    request_id: str
    refresh_token: str = field(repr=False)
    device_id: str


class Refresh:
    def __init__(
        self,
        identity: IdentityRepository,
        clock: Clock,
        digests: CodeHasher,
        secrets: SecretSource,
        tokens: TokenIssuer,
    ) -> None:
        self._identity = identity
        self._clock = clock
        self._digests = digests
        self._secrets = secrets
        self._tokens = tokens

    async def execute(self, command: RefreshCommand) -> AuthEnvelope:
        now = self._clock.now()
        replacement = self._secrets.refresh_token()
        outcome = await self._identity.refresh(
            TokenRefresh(
                request_id=command.request_id,
                token_hash=self._digests.digest(command.refresh_token),
                device_id=command.device_id,
                new_token_hash=self._digests.digest(replacement),
                now=now,
            )
        )
        return answer(
            outcome,
            device_id=command.device_id,
            refresh_token=replacement,
            tokens=self._tokens,
            now=now,
        )
