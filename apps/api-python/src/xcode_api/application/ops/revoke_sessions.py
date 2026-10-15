"""End every session of a user: security version, devices and refresh tokens."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.identity import OperatorRequest, RevokedSessions
from ..ports import Clock
from ..repositories import OpsRepository


@dataclass(frozen=True, slots=True)
class RevokeSessionsCommand:
    operator: str
    request_id: str
    email: str = field(repr=False)


class RevokeSessions:
    def __init__(self, ops: OpsRepository, clock: Clock) -> None:
        self._ops = ops
        self._clock = clock

    async def execute(self, command: RevokeSessionsCommand) -> RevokedSessions:
        return await self._ops.revoke_sessions(
            OperatorRequest(command.operator, command.request_id, command.email, self._clock.now())
        )
