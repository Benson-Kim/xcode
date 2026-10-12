"""Add a main category."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.setup import MainCategorySave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class CreateExpenseMainCategoryCommand:
    caller: Caller
    name: str | None


class CreateExpenseMainCategory:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: CreateExpenseMainCategoryCommand) -> WriteResult:
        return await self._setup.create_expense_main_category(
            MainCategorySave(command.caller.context(self._clock), None, command.name)
        )
