"""Add an expense category under a main category or none."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import ExpenseCategorySave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class CreateExpenseCategoryCommand:
    caller: Caller
    name: str | None
    main_category_id: UUID | None


class CreateExpenseCategory:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: CreateExpenseCategoryCommand) -> WriteResult:
        return await self._setup.create_expense_category(
            ExpenseCategorySave(
                command.caller.context(self._clock),
                None,
                command.name,
                command.main_category_id,
                True,
            )
        )
