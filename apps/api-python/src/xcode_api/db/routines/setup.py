"""``SetupRoutines``: the real ``SetupRepository``, one typed method per company, vehicle,
scheduled item, expense catalogue and investment routine. Reads are marked idempotent, so only
they are retried on a transient SQLSTATE; every command runs once."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from ...application.errors import IntegrityBug
from ...domain.setup import (
    CompanyChoice,
    CompanyLifecycle,
    CompanyPage,
    CompanySave,
    ExpenseCategoryPage,
    ExpenseCategorySave,
    ExpenseItemChoice,
    ExpenseItemCreate,
    ExpenseItemRename,
    ExpenseLifecycle,
    InvestmentCreate,
    InvestmentRemoval,
    InvestmentSummary,
    InvestmentUpdate,
    MainCategoryPage,
    MainCategorySave,
    RecurringCancelStop,
    RecurringDefinition,
    RecurringListQuery,
    RecurringPage,
    RecurringSave,
    RecurringStop,
    SetupPageQuery,
    ShareVehicle,
    TargetSetRemoval,
    TargetSetSave,
    TargetSetSummary,
    VehicleListQuery,
    VehiclePage,
    VehicleQuery,
    VehicleReport,
    VehicleReportQuery,
    VehicleRetirement,
    VehicleReturn,
    VehicleSave,
)
from ...domain.tenancy import TenantContext
from ...domain.values import WriteResult
from ..session import call
from ..types import document, write_result


def _tenant(context: TenantContext) -> tuple[Any, ...]:
    return (context.actor_id, context.organization_id, context.request_id)


def _amounts(values: tuple[Any, ...] | None) -> list[Any] | None:
    """Day targets as a ``numeric[]``, every value as sent (a missing one as NULL); the routine
    refuses anything but seven amounts."""
    return None if values is None else list(values)


def _definition(d: RecurringDefinition) -> tuple[Any, ...]:
    """The definition in routine order; the shares travel as a ``jsonb`` array whose amounts
    are text, so the routine reads every digit that was sent."""
    shares = Jsonb(
        [
            {
                "vehicle_id": None if s.vehicle_id is None else str(s.vehicle_id),
                "amount": None if s.amount is None else str(s.amount),
            }
            for s in d.allocations
        ]
    )
    return (
        d.name,
        d.kind,
        d.amount,
        d.frequency,
        d.day,
        d.last_day,
        d.start,
        d.end,
        shares,
        d.expense_item_id,
        d.note,
        d.month,
    )


class SetupRoutines:
    """Setup routines (``api.setup_*``)."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    # --- companies --------------------------------------------------------------------------

    async def list_companies(self, query: SetupPageQuery) -> CompanyPage:
        value = await self._read(
            "setup_company_list",
            *_tenant(query.context),
            query.page,
            query.page_size,
            query.context.now,
        )
        return document(value, CompanyPage, "api.setup_company_list")

    async def create_company(self, command: CompanySave) -> WriteResult:
        return await self._write(
            "setup_company_create",
            *_tenant(command.context),
            command.name,
            command.reason,
            command.context.now,
        )

    async def rename_company(self, command: CompanySave) -> WriteResult:
        return await self._write(
            "setup_company_rename",
            *_tenant(command.context),
            command.company_id,
            command.name,
            command.reason,
            command.context.now,
        )

    async def archive_company(self, command: CompanyLifecycle) -> WriteResult:
        return await self._write(
            "setup_company_archive",
            *_tenant(command.context),
            command.company_id,
            command.reason,
            command.context.now,
        )

    async def restore_company(self, command: CompanyLifecycle) -> WriteResult:
        return await self._write(
            "setup_company_restore",
            *_tenant(command.context),
            command.company_id,
            command.reason,
            command.context.now,
        )

    async def company_options(self, context: TenantContext) -> tuple[CompanyChoice, ...]:
        values = await self._read("setup_company_options", *_tenant(context), context.now)
        return tuple(document(v, CompanyChoice, "api.setup_company_options") for v in values)

    # --- vehicles ---------------------------------------------------------------------------

    async def list_vehicles(self, query: VehicleListQuery) -> VehiclePage:
        value = await self._read(
            "setup_vehicle_list",
            *_tenant(query.context),
            query.page,
            query.page_size,
            query.company_id,
            query.context.now,
        )
        return document(value, VehiclePage, "api.setup_vehicle_list")

    async def create_vehicle(self, command: VehicleSave) -> WriteResult:
        d = command.details
        return await self._write(
            "setup_vehicle_create",
            *_tenant(command.context),
            d.company_id,
            d.registration,
            d.fleet_number,
            d.joined_on,
            _amounts(d.day_targets),
            d.initial_investment,
            command.reason,
            command.context.now,
        )

    async def update_vehicle(self, command: VehicleSave) -> WriteResult:
        d = command.details
        return await self._write(
            "setup_vehicle_update",
            *_tenant(command.context),
            command.vehicle_id,
            d.company_id,
            d.registration,
            d.fleet_number,
            d.joined_on,
            d.initial_investment,
            command.reason,
            command.context.now,
        )

    async def retire_vehicle(self, command: VehicleRetirement) -> WriteResult:
        return await self._write(
            "setup_vehicle_retire",
            *_tenant(command.context),
            command.vehicle_id,
            command.left_on,
            command.reason,
            command.context.now,
        )

    async def restore_vehicle(self, command: VehicleReturn) -> WriteResult:
        return await self._write(
            "setup_vehicle_restore",
            *_tenant(command.context),
            command.vehicle_id,
            command.returned_on,
            command.reason,
            command.context.now,
        )

    async def vehicle_report(self, query: VehicleReportQuery) -> VehicleReport:
        value = await self._read(
            "setup_vehicle_report",
            *_tenant(query.context),
            query.vehicle_id,
            query.period,
            query.from_date,
            query.through,
            query.context.now,
        )
        return document(value, VehicleReport, "api.setup_vehicle_report")

    async def list_target_sets(self, query: VehicleQuery) -> tuple[TargetSetSummary, ...]:
        values = await self._read(
            "setup_target_set_list", *_tenant(query.context), query.vehicle_id, query.context.now
        )
        return tuple(document(v, TargetSetSummary, "api.setup_target_set_list") for v in values)

    async def save_target_set(self, command: TargetSetSave) -> WriteResult:
        return await self._write(
            "setup_target_set_save",
            *_tenant(command.context),
            command.vehicle_id,
            command.starts_on,
            _amounts(command.days),
            command.context.now,
        )

    async def remove_target_set(self, command: TargetSetRemoval) -> WriteResult:
        return await self._write(
            "setup_target_set_remove",
            *_tenant(command.context),
            command.set_id,
            command.context.now,
        )

    # --- scheduled items --------------------------------------------------------------------

    async def list_recurring(self, query: RecurringListQuery) -> RecurringPage:
        value = await self._read(
            "setup_recurring_list",
            *_tenant(query.context),
            query.page,
            query.page_size,
            query.kind,
            query.company_id,
            query.status,
            query.context.now,
        )
        return document(value, RecurringPage, "api.setup_recurring_list")

    async def vehicle_options(self, context: TenantContext) -> tuple[ShareVehicle, ...]:
        values = await self._read("setup_vehicle_options", *_tenant(context), context.now)
        return tuple(document(v, ShareVehicle, "api.setup_vehicle_options") for v in values)

    async def create_recurring(self, command: RecurringSave) -> WriteResult:
        return await self._write(
            "setup_recurring_create",
            *_tenant(command.context),
            *_definition(command.definition),
            command.reason,
            command.context.now,
        )

    async def revise_recurring(self, command: RecurringSave) -> WriteResult:
        return await self._write(
            "setup_recurring_revise",
            *_tenant(command.context),
            command.item_id,
            *_definition(command.definition),
            command.reason,
            command.context.now,
        )

    async def stop_recurring(self, command: RecurringStop) -> WriteResult:
        return await self._write(
            "setup_recurring_stop",
            *_tenant(command.context),
            command.item_id,
            command.confirmed,
            command.reason,
            command.context.now,
        )

    async def cancel_recurring_stop(self, command: RecurringCancelStop) -> WriteResult:
        return await self._write(
            "setup_recurring_cancel_stop",
            *_tenant(command.context),
            command.item_id,
            command.context.now,
        )

    # --- expense catalogue ------------------------------------------------------------------

    async def list_expense_categories(self, query: SetupPageQuery) -> ExpenseCategoryPage:
        value = await self._read(
            "setup_expense_category_list",
            *_tenant(query.context),
            query.page,
            query.page_size,
            query.context.now,
        )
        return document(value, ExpenseCategoryPage, "api.setup_expense_category_list")

    async def expense_item_options(self, context: TenantContext) -> tuple[ExpenseItemChoice, ...]:
        values = await self._read("setup_expense_item_options", *_tenant(context), context.now)
        return tuple(
            document(v, ExpenseItemChoice, "api.setup_expense_item_options") for v in values
        )

    async def create_expense_category(self, command: ExpenseCategorySave) -> WriteResult:
        return await self._write(
            "setup_expense_category_create",
            *_tenant(command.context),
            command.name,
            command.main_category_id,
            command.context.now,
        )

    async def update_expense_category(self, command: ExpenseCategorySave) -> WriteResult:
        return await self._write(
            "setup_expense_category_update",
            *_tenant(command.context),
            command.category_id,
            command.name,
            command.main_category_id,
            command.main_category_given,
            command.context.now,
        )

    async def set_expense_category_stopped(self, command: ExpenseLifecycle) -> WriteResult:
        return await self._write(
            "setup_expense_category_set_stopped",
            *_tenant(command.context),
            command.id,
            command.stopped,
            command.context.now,
        )

    async def create_expense_item(self, command: ExpenseItemCreate) -> WriteResult:
        return await self._write(
            "setup_expense_item_create",
            *_tenant(command.context),
            command.category_id,
            command.name,
            command.context.now,
        )

    async def rename_expense_item(self, command: ExpenseItemRename) -> WriteResult:
        return await self._write(
            "setup_expense_item_rename",
            *_tenant(command.context),
            command.item_id,
            command.name,
            command.context.now,
        )

    async def set_expense_item_stopped(self, command: ExpenseLifecycle) -> WriteResult:
        return await self._write(
            "setup_expense_item_set_stopped",
            *_tenant(command.context),
            command.id,
            command.stopped,
            command.context.now,
        )

    async def list_expense_main_categories(self, query: SetupPageQuery) -> MainCategoryPage:
        value = await self._read(
            "setup_expense_main_category_list",
            *_tenant(query.context),
            query.page,
            query.page_size,
            query.context.now,
        )
        return document(value, MainCategoryPage, "api.setup_expense_main_category_list")

    async def create_expense_main_category(self, command: MainCategorySave) -> WriteResult:
        return await self._write(
            "setup_expense_main_category_create",
            *_tenant(command.context),
            command.name,
            command.context.now,
        )

    async def rename_expense_main_category(self, command: MainCategorySave) -> WriteResult:
        return await self._write(
            "setup_expense_main_category_rename",
            *_tenant(command.context),
            command.main_category_id,
            command.name,
            command.context.now,
        )

    # --- investment -------------------------------------------------------------------------

    async def get_investment(self, query: VehicleQuery) -> InvestmentSummary:
        value = await self._read(
            "setup_investment_get", *_tenant(query.context), query.vehicle_id, query.context.now
        )
        return document(value, InvestmentSummary, "api.setup_investment_get")

    async def create_investment(self, command: InvestmentCreate) -> WriteResult:
        d = command.details
        return await self._write(
            "setup_investment_create",
            *_tenant(command.context),
            command.vehicle_id,
            d.invested_on,
            d.description,
            d.amount,
            command.context.now,
        )

    async def update_investment(self, command: InvestmentUpdate) -> WriteResult:
        d = command.details
        return await self._write(
            "setup_investment_update",
            *_tenant(command.context),
            command.entry_id,
            d.invested_on,
            d.description,
            d.amount,
            command.context.now,
        )

    async def delete_investment(self, command: InvestmentRemoval) -> WriteResult:
        return await self._write(
            "setup_investment_delete",
            *_tenant(command.context),
            command.entry_id,
            command.context.now,
        )

    async def _read(self, routine: str, *args: Any) -> Any:
        rows = await call(self._pool, routine, *args, idempotent=True)
        if len(rows) != 1 or routine not in rows[0] or rows[0][routine] is None:
            raise IntegrityBug(f"api.{routine} returned no single value")
        return rows[0][routine]

    async def _write(self, routine: str, *args: Any) -> WriteResult:
        rows = await call(self._pool, routine, *args)
        if len(rows) != 1:
            raise IntegrityBug(f"api.{routine} returned {len(rows)} rows, expected one")
        return write_result(rows[0])
