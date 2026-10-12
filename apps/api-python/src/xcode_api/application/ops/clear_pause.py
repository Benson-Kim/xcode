"""Clear a sign-in pause (never the untrusted-device cap)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.identity import ClearedPause, OperatorRequest
from ..ports import Clock
from ..repositories import OpsRepository


@dataclass(frozen=True, slots=True)
class ClearPauseCommand:
    operator: str
    request_id: str
    email: str = field(repr=False)


class ClearPause:
    def __init__(self, ops: OpsRepository, clock: Clock) -> None:
        self._ops = ops
        self._clock = clock

    async def execute(self, command: ClearPauseCommand) -> ClearedPause:
        return await self._ops.clear_pause(
            OperatorRequest(command.operator, command.request_id, command.email, self._clock.now())
        )
