"""Authenticate a bearer request: verify the access token, then resolve the session against
the database (user active, security version current, device trusted), with no cache. Any
failure raises ``SessionInvalid``."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.identity import Principal, SessionCheck, TokenClaims
from ..ports import Clock, TokenIssuer
from ..repositories import IdentityRepository


@dataclass(frozen=True, slots=True)
class ResolveSessionCommand:
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ResolvedSession:
    principal: Principal
    claims: TokenClaims


class ResolveSession:
    def __init__(self, tokens: TokenIssuer, identity: IdentityRepository, clock: Clock) -> None:
        self._tokens = tokens
        self._identity = identity
        self._clock = clock

    async def execute(self, command: ResolveSessionCommand) -> ResolvedSession:
        now = self._clock.now()
        claims = self._tokens.verify(command.token, now=now)
        context = await self._identity.resolve_session(
            SessionCheck(claims.user_id, claims.device_id, claims.security_version, now)
        )
        principal = Principal(
            user_id=claims.user_id,
            device_id=claims.device_id,
            security_version=claims.security_version,
            organization_id=context.organization_id,
            role=context.role,
            permissions=claims.permissions,
        )
        return ResolvedSession(principal=principal, claims=claims)
