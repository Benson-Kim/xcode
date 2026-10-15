"""``RevenueRoutines``: the real ``RevenueRepository``. The two reads are marked idempotent, so
only they are retried on a transient SQLSTATE; a capture runs once (a retried capture whose
first attempt committed would answer ``replayed``, but a timeout is not proof of either)."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from ...application.errors import IntegrityBug
from ...domain.revenue import (
    CaptureOutcome,
    CaptureResult,
    RevenueCapture,
    RevenueDashboard,
    RevenueDashboardQuery,
    RevenueDay,
    RevenueDayQuery,
    RevenueDayResult,
    RevenueDaySave,
    RevenueWeek,
    RevenueWeekQuery,
)
from ...domain.tenancy import TenantContext
from ..session import call
from ..types import document, write_result


def _tenant(context: TenantContext) -> tuple[Any, ...]:
    return (context.actor_id, context.organization_id, context.request_id)


class RevenueRoutines:
    """Revenue routines (``api.revenue_*``)."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def week(self, query: RevenueWeekQuery) -> RevenueWeek:
        value = await self._read(
            "revenue_week_get",
            *_tenant(query.context),
            query.week_start,
            query.company_id,
            query.vehicle_id,
            query.page,
            query.page_size,
            query.q,
            query.context.now,
        )
        return document(value, RevenueWeek, "api.revenue_week_get")

    async def dashboard(self, query: RevenueDashboardQuery) -> RevenueDashboard:
        value = await self._read(
            "revenue_dashboard_get",
            *_tenant(query.context),
            query.period,
            query.company_id,
            query.context.now,
        )
        return document(value, RevenueDashboard, "api.revenue_dashboard_get")

    async def capture(self, command: RevenueCapture) -> CaptureResult:
        rows = await call(
            self._pool,
            "revenue_capture",
            *_tenant(command.context),
            command.vehicle_id,
            command.day,
            command.amount,
            command.reason,
            command.note,
            command.expected_version,
            command.captured_at,
            command.context.now,
        )
        if len(rows) != 1:
            raise IntegrityBug(f"api.revenue_capture returned {len(rows)} rows, expected one")
        result = write_result(rows[0])
        try:
            outcome = CaptureOutcome(result.outcome.value)
        except ValueError:
            raise IntegrityBug(f"api.revenue_capture answered {result.outcome}") from None
        return CaptureResult(id=result.id, version=result.version, outcome=outcome)

    async def day(self, query: RevenueDayQuery) -> RevenueDay:
        value = await self._read(
            "revenue_day_get",
            *_tenant(query.context),
            query.day,
            query.company_id,
            query.context.now,
        )
        return document(value, RevenueDay, "api.revenue_day_get")

    async def save_day(self, command: RevenueDaySave) -> RevenueDayResult:
        """The rows travel as a ``jsonb`` array whose amounts and versions are text, so the
        routine reads every digit that was sent; a day save runs once, like a capture."""
        rows = Jsonb(
            [
                {
                    "vehicle_id": None if r.vehicle_id is None else str(r.vehicle_id),
                    "amount": None if r.amount is None else format(r.amount, "f"),
                    "reason": r.reason,
                    "note": r.note,
                    "version": None if r.version is None else str(r.version),
                }
                for r in command.rows
            ]
        )
        found = await call(
            self._pool,
            "revenue_day_save",
            *_tenant(command.context),
            command.day,
            rows,
            command.context.now,
        )
        if len(found) != 1 or found[0].get("revenue_day_save") is None:
            raise IntegrityBug("api.revenue_day_save returned no single value")
        return document(found[0]["revenue_day_save"], RevenueDayResult, "api.revenue_day_save")

    async def _read(self, routine: str, *args: Any) -> Any:
        rows = await call(self._pool, routine, *args, idempotent=True)
        if len(rows) != 1 or routine not in rows[0] or rows[0][routine] is None:
            raise IntegrityBug(f"api.{routine} returned no single value")
        return rows[0][routine]
