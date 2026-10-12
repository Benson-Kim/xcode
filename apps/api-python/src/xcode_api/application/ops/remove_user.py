"""Remove a user: status removed, every access and refresh token ends."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.identity import OperatorRequest, RemovedUser
from ..ports import Clock
from ..repositories import OpsRepository


@dataclass(frozen=True, slots=True)
class RemoveUserCommand:
    operator: str
    request_id: str
    email: str = field(repr=False)


class RemoveUser:
    def __init__(self, ops: OpsRepository, clock: Clock) -> None:
        self._ops = ops
        self._clock = clock

    async def execute(self, command: RemoveUserCommand) -> RemovedUser:
        return await self._ops.remove_user(
            OperatorRequest(command.operator, command.request_id, command.email, self._clock.now())
        )
