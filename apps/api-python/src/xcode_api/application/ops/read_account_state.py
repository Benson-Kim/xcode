"""Read what a support call needs about an account; never a hash or digest."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.identity import AccountSummary, OperatorRequest
from ..ports import Clock
from ..repositories import OpsRepository


@dataclass(frozen=True, slots=True)
class ReadAccountStateCommand:
    operator: str
    request_id: str
    email: str = field(repr=False)


class ReadAccountState:
    def __init__(self, ops: OpsRepository, clock: Clock) -> None:
        self._ops = ops
        self._clock = clock

    async def execute(self, command: ReadAccountStateCommand) -> AccountSummary:
        return await self._ops.account_state(
            OperatorRequest(command.operator, command.request_id, command.email, self._clock.now())
        )
