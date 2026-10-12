"""Remove a target set that has not started."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import TargetSetRemoval
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class RemoveTargetSetCommand:
    caller: Caller
    set_id: UUID


class RemoveTargetSet:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: RemoveTargetSetCommand) -> WriteResult:
        return await self._setup.remove_target_set(
            TargetSetRemoval(command.caller.context(self._clock), command.set_id)
        )
