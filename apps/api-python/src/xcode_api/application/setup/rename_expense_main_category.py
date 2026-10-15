"""Rename a main category."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.setup import MainCategorySave
from ...domain.values import WriteResult
from ..caller import Caller
from ..ports import Clock
from ..repositories import SetupRepository


@dataclass(frozen=True, slots=True)
class RenameExpenseMainCategoryCommand:
    caller: Caller
    main_category_id: UUID
    name: str | None


class RenameExpenseMainCategory:
    def __init__(self, setup: SetupRepository, clock: Clock) -> None:
        self._setup = setup
        self._clock = clock

    async def execute(self, command: RenameExpenseMainCategoryCommand) -> WriteResult:
        return await self._setup.rename_expense_main_category(
            MainCategorySave(
                command.caller.context(self._clock), command.main_category_id, command.name
            )
        )
