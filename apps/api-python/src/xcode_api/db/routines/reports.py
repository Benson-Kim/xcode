"""``ReportsRoutines``: the real ``ReportsRepository``. Every call is a read or an export,
and every export reads its rows and writes its audit row in one transaction, so all of them
are marked idempotent: a retried export after a transient failure is a new transaction whose
earlier row rolled back with it (``docs/05-routines.md`` 11.4). Money cells arrive as JSON
numbers and are read back as decimals; nothing is summed here."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from psycopg_pool import AsyncConnectionPool

from ...application.errors import IntegrityBug
from ...domain.reports import (
    ExpenseExportQuery,
    PettyCashExportQuery,
    ReportDocument,
    ReportExportQuery,
    ReportQuery,
    ReportsAccess,
    ReportTable,
    RevenueExportQuery,
)
from ...domain.tenancy import TenantContext
from ..session import call
from ..types import document


def _tenant(context: TenantContext) -> tuple[Any, ...]:
    return (context.actor_id, context.organization_id, context.request_id)


def _words(words: tuple[str, ...] | None) -> list[str] | None:
    return None if words is None else list(words)


def _decimal_cells(value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("rows"), list):
        value = dict(value)
        value["rows"] = [
            [Decimal(repr(cell)) if isinstance(cell, float) else cell for cell in row]
            for row in value["rows"]
        ]
    return value


class ReportsRoutines:
    """Report and export routines (``api.report_*``, the three screen exports)."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def access(self, context: TenantContext) -> ReportsAccess:
        value = await self._read("report_catalog_get", *_tenant(context), context.now)
        return document(value, ReportsAccess, "api.report_catalog_get")

    async def report(self, query: ReportQuery) -> ReportTable:
        value = await self._read(
            "report_get",
            *_tenant(query.context),
            query.group,
            query.report,
            query.from_date,
            query.to_date,
            query.company_id,
            query.holder_id,
            query.q,
            query.page,
            query.page_size,
            query.context.now,
        )
        return document(_decimal_cells(value), ReportTable, "api.report_get")

    async def export_report(self, query: ReportExportQuery) -> ReportDocument:
        value = await self._read(
            "report_export_get",
            *_tenant(query.context),
            query.group,
            query.report,
            query.from_date,
            query.to_date,
            query.company_id,
            query.holder_id,
            query.q,
            query.format,
            query.context.now,
        )
        return document(_decimal_cells(value), ReportDocument, "api.report_export_get")

    async def export_revenue(self, query: RevenueExportQuery) -> ReportDocument:
        value = await self._read(
            "revenue_export_get",
            *_tenant(query.context),
            query.week_start,
            query.company_id,
            query.format,
            query.context.now,
        )
        return document(_decimal_cells(value), ReportDocument, "api.revenue_export_get")

    async def export_expenses(self, query: ExpenseExportQuery) -> ReportDocument:
        value = await self._read(
            "expenses_export_get",
            *_tenant(query.context),
            query.from_date,
            query.to_date,
            query.source,
            query.q,
            query.format,
            query.context.now,
        )
        return document(_decimal_cells(value), ReportDocument, "api.expenses_export_get")

    async def export_pettycash(self, query: PettyCashExportQuery) -> ReportDocument:
        value = await self._read(
            "pettycash_export_get",
            *_tenant(query.context),
            query.from_date,
            query.to_date,
            query.holder_id,
            query.view,
            _words(query.statuses),
            query.q,
            query.format,
            query.context.now,
        )
        return document(_decimal_cells(value), ReportDocument, "api.pettycash_export_get")

    async def _read(self, routine: str, *args: Any) -> Any:
        rows = await call(self._pool, routine, *args, idempotent=True)
        if len(rows) != 1 or routine not in rows[0] or rows[0][routine] is None:
            raise IntegrityBug(f"api.{routine} returned no single value")
        return rows[0][routine]
