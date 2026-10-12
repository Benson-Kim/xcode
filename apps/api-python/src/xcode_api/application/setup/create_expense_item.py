"""Add an expense item under a category."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import ExpenseItemCreate
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class CreateExpenseItemCommand:
    caller: Caller
    category_id: UUID
    name: str | None


class CreateExpenseItem:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: CreateExpenseItemCommand) -> WriteResult:
        return await self._setup.create_expense_item(
            ExpenseItemCreate(
                command.caller.context(self._clock), command.category_id, command.name
            )
        )
