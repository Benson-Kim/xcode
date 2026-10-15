"""``ExpensesRoutines``: the real ``ExpensesRepository``. The two reads are marked idempotent,
so only they are retried on a transient SQLSTATE; a write runs once (a retried record would
answer its rows, but a timeout is not proof that the first attempt committed)."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from ...application.errors import IntegrityBug
from ...domain.expenses import (
    ExpenseAllocation,
    ExpenseChange,
    ExpenseLedger,
    ExpenseLedgerQuery,
    ExpenseOptions,
    ExpenseOptionsQuery,
    ExpensePurchase,
    ExpenseRecorded,
    ExpenseRemoval,
    ExpenseSaved,
)
from ...domain.tenancy import TenantContext
from ..session import call
from ..types import document


def _tenant(context: TenantContext) -> tuple[Any, ...]:
    return (context.actor_id, context.organization_id, context.request_id)


def allocations_argument(allocations: tuple[ExpenseAllocation, ...] | None) -> Jsonb | None:
    """``p_allocations``: amounts as decimal text, so the routine reads them exactly."""
    if allocations is None:
        return None
    return Jsonb(
        [
            {
                "vehicle_id": None if a.vehicle_id is None else str(a.vehicle_id),
                "amount": None if a.amount is None else str(a.amount),
            }
            for a in allocations
        ]
    )


class ExpensesRoutines:
    """Central-expense routines (``api.expenses_*``)."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def ledger(self, query: ExpenseLedgerQuery) -> ExpenseLedger:
        value = await self._call(
            "expenses_ledger_get",
            *_tenant(query.context),
            query.from_date,
            query.to_date,
            query.source,
            query.q,
            query.page,
            query.page_size,
            query.context.now,
            idempotent=True,
        )
        return document(value, ExpenseLedger, "api.expenses_ledger_get")

    async def options(self, query: ExpenseOptionsQuery) -> ExpenseOptions:
        value = await self._call(
            "expenses_options_get",
            *_tenant(query.context),
            query.day,
            query.context.now,
            idempotent=True,
        )
        return document(value, ExpenseOptions, "api.expenses_options_get")

    async def record(self, command: ExpensePurchase) -> ExpenseRecorded:
        value = await self._call(
            "expenses_entry_create",
            *_tenant(command.context),
            command.id,
            command.day,
            command.expense_item_id,
            command.units,
            command.unit_amount,
            command.note,
            allocations_argument(command.allocations),
            command.context.now,
        )
        return document(value, ExpenseRecorded, "api.expenses_entry_create")

    async def change(self, command: ExpenseChange) -> ExpenseSaved:
        value = await self._call(
            "expenses_entry_update",
            *_tenant(command.context),
            command.entry_id,
            command.day,
            command.vehicle_id,
            command.expense_item_id,
            command.units,
            command.unit_amount,
            command.note,
            command.expected_version,
            command.context.now,
        )
        return document(value, ExpenseSaved, "api.expenses_entry_update")

    async def remove(self, command: ExpenseRemoval) -> ExpenseSaved:
        value = await self._call(
            "expenses_entry_remove",
            *_tenant(command.context),
            command.entry_id,
            command.expected_version,
            command.reason,
            command.context.now,
        )
        return document(value, ExpenseSaved, "api.expenses_entry_remove")

    async def _call(self, routine: str, *args: Any, idempotent: bool = False) -> Any:
        rows = await call(self._pool, routine, *args, idempotent=idempotent)
        if len(rows) != 1 or routine not in rows[0] or rows[0][routine] is None:
            raise IntegrityBug(f"api.{routine} returned no single value")
        return rows[0][routine]
