"""Company, vehicle, scheduled item, expense catalogue, investment and vehicle report contract
models (``docs/inventory/inventory-http-contract.md`` sections 3.4 and 3.5): field order is
the wire order, names are the camelCase aliases of the fields unless an alias says otherwise.
``kind``, ``frequency`` and ``bucket`` are the integer codes.

Request fields a client may leave out default to null (or the .NET default for a number or a
flag), and the routine refuses what is missing with its own sentence; amounts are read exactly
and checked by the routine, so a third decimal place gets the money sentence, not a binding
error."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import Field

from ...domain.setup import (
    InvestmentDetails,
    OpeningAmount,
    RecurringDefinition,
    SavingCondition,
    SavingOpening,
    Share,
    VehicleDetails,
)
from .common import Amount, ApiModel, Instant, Money, Page

Int32 = Annotated[int, Field(ge=-(2**31), le=2**31 - 1)]


# --- companies and vehicles ---------------------------------------------------------------


class CompanyDto(ApiModel):
    id: UUID
    name: str
    vehicle_count: int
    active: bool
    archived_on: date | None


class TargetDto(ApiModel):
    effective_from: date
    weekly_amount: Money
    revision: int


class AwayPeriodDto(ApiModel):
    left_on: date
    returned_on: date


class NextTargetDto(ApiModel):
    starts_on: date
    day_targets: list[Money]
    weekly_target: Money


class VehicleDto(ApiModel):
    """``weeklyTarget``, ``recurringItems``, ``dayTargets`` and ``nextTarget`` are null, and
    ``targets`` empty, for an investment viewer without ``vehicles.view``. ``weeklyTarget`` is
    the total of the set in force today; ``targets`` is one entry per target set in the shape
    released clients read; ``dayTargets`` is Monday first."""

    id: UUID
    company_id: UUID
    company_name: str
    registration: str
    joined_on: date
    left_on: date | None
    active: bool
    weekly_target: Money | None
    targets: list[TargetDto]
    recurring_items: int | None
    away: list[AwayPeriodDto]
    fleet_number: str | None
    initial_investment: Money | None
    day_targets: list[Money] | None
    next_target: NextTargetDto | None


class TargetSetDto(ApiModel):
    id: UUID
    starts_on: date
    days: list[Money]
    week_total: Money
    in_force: bool
    can_remove: bool


class SaveTargetSet(ApiModel):
    """``POST /setup/vehicles/{id}/targets``: ``days`` Monday first; the routine refuses
    anything but seven amounts."""

    starts_on: date | None = None
    days: list[Amount | None] | None = None

    def day_amounts(self) -> tuple[Decimal | None, ...] | None:
        return None if self.days is None else tuple(self.days)


class SaveCompany(ApiModel):
    name: str | None = None
    reason: str | None = None


class CompanyLifecycleRequest(ApiModel):
    reason: str | None = None


class SaveVehicle(ApiModel):
    """``POST /setup/vehicles`` and ``PUT /setup/vehicles/{id}``. ``dayTargets`` (Monday
    first) is read on a new vehicle only; a ``weeklyTarget`` released clients send is ignored,
    targets change through a target set. An ``initialInvestment`` of 0 or null is empty."""

    company_id: UUID | None = None
    registration: str | None = None
    joined_on: date | None = None
    reason: str | None = None
    fleet_number: str | None = None
    day_targets: list[Amount | None] | None = None
    initial_investment: Amount | None = None

    def details(self) -> VehicleDetails:
        return VehicleDetails(
            company_id=self.company_id,
            registration=self.registration,
            fleet_number=self.fleet_number,
            joined_on=self.joined_on,
            day_targets=None if self.day_targets is None else tuple(self.day_targets),
            initial_investment=self.initial_investment,
        )


class VehicleLifecycleRequest(ApiModel):
    left_on: date | None = None
    reason: str | None = None


class VehicleRestoreRequest(ApiModel):
    reason: str | None = None
    returned_on: date | None = None


class PostingDto(ApiModel):
    item_id: UUID
    version_id: UUID
    day: date = Field(alias="date")
    name: str
    kind: int
    amount: Money
    bucket: int | None
    source: str | None


class VehicleReportDto(ApiModel):
    vehicle_id: UUID
    from_date: date = Field(alias="from")
    through: date
    money_in: Money
    target: Money
    repairs: Money
    charges: Money
    loans: Money
    money_out: Money
    net: Money
    savings: Money
    after_savings: Money
    costs: Money
    postings: list[PostingDto]


# --- scheduled expenses and savings -------------------------------------------------------


class AllocationDto(ApiModel):
    vehicle_id: UUID
    amount: Money
    registration: str | None
    active: bool


class RunStatesDto(ApiModel):
    saved: int
    skipped: int
    held: int


class RevenueRuleDto(ApiModel):
    min: Money
    days: int


class OpeningSummaryDto(ApiModel):
    opened_on: date = Field(alias="date")
    total: Money


class RecurringDto(ApiModel):
    id: UUID
    version_id: UUID
    revision: int
    name: str
    kind: int
    amount: Money
    frequency: int
    day: int | None
    last_day: bool
    start_on: date = Field(alias="start")
    end_on: date | None = Field(alias="end")
    stopped_from: date | None
    allocations: list[AllocationDto]
    partial: bool
    expense_item_id: UUID | None
    expense_item_name: str | None
    bucket: int | None
    note: str | None
    month: int | None
    active_amount: Money
    paused_from: date | None
    last_run: date | None
    last_run_vehicles: int
    balance: Money | None
    last_run_states: RunStatesDto | None
    condition: RevenueRuleDto | None
    opening: OpeningSummaryDto | None
    next_run: date | None


class RecurringRunShareDto(ApiModel):
    vehicle_id: UUID
    registration: str
    amount: Money
    state: str
    revenue: Money | None


class RecurringRunDto(ApiModel):
    run_on: date = Field(alias="date")
    amount: Money
    shares: list[RecurringRunShareDto]


class RecurringRunsDto(ApiModel):
    """``GET /setup/recurring/{id}/runs``."""

    id: UUID
    name: str
    kind: int
    start: date
    total: Money
    run_count: int
    runs: list[RecurringRunDto]


class RecurringSummaryDto(ApiModel):
    """``GET /setup/recurring/summary``: a figure of a kind the caller cannot view is null."""

    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    costs_due: Money | None
    saved: Money | None
    savings_balance: Money | None
    running_costs: int | None
    paused_costs: int | None
    running_savings: int | None
    paused_savings: int | None


class RecurringVehicleOption(ApiModel):
    """A vehicle a scheduled item's share can use (``VehicleOption`` in the .NET contract)."""

    id: UUID
    company_id: UUID
    company_name: str
    registration: str
    active: bool
    fleet_number: str | None


class ShareRequest(ApiModel):
    vehicle_id: UUID | None = None
    amount: Amount | None = None


class ConditionRequest(ApiModel):
    min: Amount | None = None
    days: Int32 | None = None


class OpeningAmountRequest(ApiModel):
    vehicle_id: UUID | None = None
    amount: Amount | None = None


class OpeningRequest(ApiModel):
    opened_on: date | None = Field(default=None, alias="date")
    amounts: list[OpeningAmountRequest] = Field(default_factory=list)


class SaveRecurring(ApiModel):
    """``POST /setup/recurring`` and ``PUT /setup/recurring/{id}``; a ``category`` the older
    web still sends is ignored. A saving's ``condition`` and ``opening``: an ``opening`` absent
    from a revise keeps the stored one, null removes it."""

    name: str | None = None
    kind: Int32 = 0
    amount: Amount | None = None
    frequency: Int32 = 0
    day: Int32 | None = None
    last_day: bool = False
    start: date | None = None
    end: date | None = None
    allocations: list[ShareRequest] = Field(default_factory=list)
    reason: str | None = None
    expense_item_id: UUID | None = None
    note: str | None = None
    month: Int32 | None = None
    condition: ConditionRequest | None = None
    opening: OpeningRequest | None = None

    def definition(self) -> RecurringDefinition:
        return RecurringDefinition(
            name=self.name,
            kind=self.kind,
            amount=self.amount,
            frequency=self.frequency,
            day=self.day,
            last_day=self.last_day,
            start=self.start,
            end=self.end,
            allocations=tuple(Share(s.vehicle_id, s.amount) for s in self.allocations),
            expense_item_id=self.expense_item_id,
            note=self.note,
            month=self.month,
            condition=None
            if self.condition is None
            else SavingCondition(self.condition.min, self.condition.days),
            opening=None
            if self.opening is None
            else SavingOpening(
                self.opening.opened_on,
                tuple(OpeningAmount(a.vehicle_id, a.amount) for a in self.opening.amounts),
            ),
            keep_opening="opening" not in self.model_fields_set,
        )


class StopRecurring(ApiModel):
    confirmed: bool = False
    reason: str | None = None


# --- expense catalogue --------------------------------------------------------------------


class ExpenseItemDto(ApiModel):
    id: UUID
    category_id: UUID
    name: str
    active: bool
    stopped_on: date | None


class ExpenseCategoryDto(ApiModel):
    """``bucket`` as stored: null for a category made since main categories."""

    id: UUID
    name: str
    bucket: int | None
    active: bool
    stopped_on: date | None
    items: list[ExpenseItemDto]
    main_category_id: UUID | None
    main_category_name: str | None


class ExpenseItemOption(ApiModel):
    id: UUID
    name: str
    category_id: UUID
    category_name: str
    bucket: int | None
    main_category_id: UUID | None
    main_category_name: str | None


class SaveExpenseCategory(ApiModel):
    """A ``bucket`` released clients send is ignored. On an update an absent
    ``mainCategoryId`` leaves the main category as it is and null removes it."""

    name: str | None = None
    main_category_id: UUID | None = None

    def main_category_given(self) -> bool:
        return "main_category_id" in self.model_fields_set


class MainCategoryDto(ApiModel):
    id: UUID
    name: str
    category_count: int
    item_count: int


class MainCategoryPage(Page[MainCategoryDto]):
    categories_without_main: int


class SaveMainCategory(ApiModel):
    name: str | None = None


class SaveExpenseItem(ApiModel):
    name: str | None = None


# --- investment ---------------------------------------------------------------------------


class InvestmentEntryDto(ApiModel):
    id: UUID
    invested_on: date = Field(alias="date")
    description: str
    amount: Money
    recorded_by: str
    recorded_at: Instant


class InvestmentDto(ApiModel):
    vehicle_id: UUID
    total_invested: Money
    returned: Money | None
    percent_paid_off: Amount | None
    entries: list[InvestmentEntryDto]


class SaveInvestment(ApiModel):
    invested_on: date | None = Field(default=None, alias="date")
    description: str | None = None
    amount: Amount | None = None

    def details(self) -> InvestmentDetails:
        return InvestmentDetails(
            invested_on=self.invested_on, description=self.description, amount=self.amount
        )
