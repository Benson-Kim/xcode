"""Rename an expense category or move it to another main category or none."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import ExpenseCategorySave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class UpdateExpenseCategoryCommand:
    """``main_category_given`` False leaves the main category as it is."""

    caller: Caller
    category_id: UUID
    name: str | None
    main_category_id: UUID | None
    main_category_given: bool


class UpdateExpenseCategory:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: UpdateExpenseCategoryCommand) -> WriteResult:
        return await self._setup.update_expense_category(
            ExpenseCategorySave(
                command.caller.context(self._clock),
                command.category_id,
                command.name,
                command.main_category_id,
                command.main_category_given,
            )
        )
