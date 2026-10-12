"""``PettyCashRoutines``: the real ``PettyCashRepository``. The four reads are marked
idempotent, so only they are retried on a transient SQLSTATE; a write runs once (a retried
create whose first attempt committed would answer ``replayed``, but a timeout is not proof of
either)."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from ...application.errors import IntegrityBug
from ...domain.pettycash import (
    PettyCashApproved,
    PettyCashCreate,
    PettyCashDashboard,
    PettyCashDayApproval,
    PettyCashDecision,
    PettyCashEntriesApproval,
    PettyCashEntryPage,
    PettyCashEntryQuery,
    PettyCashLine,
    PettyCashOptions,
    PettyCashOptionsQuery,
    PettyCashOverview,
    PettyCashOverviewQuery,
    PettyCashSaved,
    PettyCashUpdate,
)
from ...domain.tenancy import TenantContext
from ..session import call
from ..types import document


def _tenant(context: TenantContext) -> tuple[Any, ...]:
    return (context.actor_id, context.organization_id, context.request_id)


def _line(line: PettyCashLine) -> tuple[Any, ...]:
    return (
        line.kind,
        line.day,
        line.unit_amount,
        line.holder_id,
        line.vehicle_id,
        line.expense_item_id,
        line.units,
        line.payee,
        line.note,
        line.reimbursable,
    )


def _words(words: tuple[str, ...] | None) -> list[str] | None:
    return None if words is None else list(words)


class PettyCashRoutines:
    """Petty-cash routines (``api.pettycash_*``)."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def overview(self, query: PettyCashOverviewQuery) -> PettyCashOverview:
        value = await self._call(
            "pettycash_overview_get",
            *_tenant(query.context),
            query.day,
            query.period,
            query.holder_id,
            query.from_date,
            query.to_date,
            query.context.now,
            idempotent=True,
        )
        return document(value, PettyCashOverview, "api.pettycash_overview_get")

    async def entries(self, query: PettyCashEntryQuery) -> PettyCashEntryPage:
        value = await self._call(
            "pettycash_entry_list",
            *_tenant(query.context),
            query.from_date,
            query.to_date,
            query.holder_id,
            _words(query.kinds),
            _words(query.statuses),
            query.q,
            query.page,
            query.page_size,
            query.context.now,
            idempotent=True,
        )
        return document(value, PettyCashEntryPage, "api.pettycash_entry_list")

    async def options(self, query: PettyCashOptionsQuery) -> PettyCashOptions:
        value = await self._call(
            "pettycash_options_get",
            *_tenant(query.context),
            query.day,
            query.context.now,
            idempotent=True,
        )
        return document(value, PettyCashOptions, "api.pettycash_options_get")

    async def dashboard(self, context: TenantContext) -> PettyCashDashboard:
        value = await self._call(
            "pettycash_dashboard_get", *_tenant(context), context.now, idempotent=True
        )
        return document(value, PettyCashDashboard, "api.pettycash_dashboard_get")

    async def create(self, command: PettyCashCreate) -> PettyCashSaved:
        return await self._saved(
            "pettycash_entry_create",
            *_tenant(command.context),
            command.id,
            *_line(command.line),
            command.context.now,
        )

    async def update(self, command: PettyCashUpdate) -> PettyCashSaved:
        return await self._saved(
            "pettycash_entry_update",
            *_tenant(command.context),
            command.entry_id,
            *_line(command.line),
            command.expected_version,
            command.context.now,
        )

    async def approve(self, command: PettyCashDecision) -> PettyCashSaved:
        return await self._saved(
            "pettycash_entry_approve",
            *_tenant(command.context),
            command.entry_id,
            command.expected_version,
            command.context.now,
        )

    async def send_back(self, command: PettyCashDecision) -> PettyCashSaved:
        return await self._decided("pettycash_entry_send_back", command)

    async def reject(self, command: PettyCashDecision) -> PettyCashSaved:
        return await self._decided("pettycash_entry_reject", command)

    async def reopen(self, command: PettyCashDecision) -> PettyCashSaved:
        return await self._decided("pettycash_entry_reopen", command)

    async def remove(self, command: PettyCashDecision) -> PettyCashSaved:
        return await self._decided("pettycash_entry_remove", command)

    async def approve_day(self, command: PettyCashDayApproval) -> PettyCashApproved:
        value = await self._call(
            "pettycash_day_approve",
            *_tenant(command.context),
            command.day,
            command.to,
            command.holder_id,
            command.context.now,
        )
        return document(value, PettyCashApproved, "api.pettycash_day_approve")

    async def approve_entries(self, command: PettyCashEntriesApproval) -> PettyCashApproved:
        ticked = Jsonb([{"id": str(t.id), "version": t.version} for t in command.entries])
        value = await self._call(
            "pettycash_entries_approve", *_tenant(command.context), ticked, command.context.now
        )
        return document(value, PettyCashApproved, "api.pettycash_entries_approve")

    async def _decided(self, routine: str, command: PettyCashDecision) -> PettyCashSaved:
        return await self._saved(
            routine,
            *_tenant(command.context),
            command.entry_id,
            command.expected_version,
            command.text,
            command.context.now,
        )

    async def _saved(self, routine: str, *args: Any) -> PettyCashSaved:
        value = await self._call(routine, *args)
        return document(value, PettyCashSaved, f"api.{routine}")

    async def _call(self, routine: str, *args: Any, idempotent: bool = False) -> Any:
        rows = await call(self._pool, routine, *args, idempotent=idempotent)
        if len(rows) != 1 or routine not in rows[0] or rows[0][routine] is None:
            raise IntegrityBug(f"api.{routine} returned no single value")
        return rows[0][routine]
