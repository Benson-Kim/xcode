"""Delete a main category, category, item, vehicle or company that nothing refers to."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import SetupRecord, SetupRecordRemoval
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class DeleteSetupRecordCommand:
    caller: Caller
    record: SetupRecord
    id: UUID


class DeleteSetupRecord:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: DeleteSetupRecordCommand) -> WriteResult:
        return await self._setup.delete_setup_record(
            SetupRecordRemoval(command.caller.context(self._clock), command.record, command.id)
        )
