"""Rename an expense item."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import ExpenseItemRename
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class RenameExpenseItemCommand:
    caller: Caller
    item_id: UUID
    name: str | None


class RenameExpenseItem:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: RenameExpenseItemCommand) -> WriteResult:
        return await self._setup.rename_expense_item(
            ExpenseItemRename(command.caller.context(self._clock), command.item_id, command.name)
        )
