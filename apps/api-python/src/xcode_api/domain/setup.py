"""Setup vocabulary: companies, vehicles and their dated history, recurring items, the
expense catalogue; the records the setup routines answer and the commands they take.

The ``IntEnum`` values are the integers the wire sends and the code tables hold;
``tests/db/test_enum_parity.py`` proves code, name and label against each code table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import IntEnum, StrEnum
from uuid import UUID

from .tenancy import TenantContext
from .values import CodedEnum


class RecurringKind(CodedEnum):
    COST = 1
    SAVINGS = 2

    @property
    def label(self) -> str:
        return _KIND_LABELS[self]


class RecurrenceFrequency(CodedEnum):
    """``DAILY`` is refused for a new cost; a saving may run daily."""

    DAILY = 1
    WEEKLY = 2
    MONTHLY = 3
    YEARLY = 4

    @property
    def label(self) -> str:
        return _FREQUENCY_LABELS[self]


class ExpenseBucket(CodedEnum):
    REPAIRS_AND_MAINTENANCE = 1
    RECURRING_CHARGES = 2
    LOAN_REPAYMENTS = 3

    @property
    def label(self) -> str:
        return _BUCKET_LABELS[self]


_KIND_LABELS = {RecurringKind.COST: "Cost", RecurringKind.SAVINGS: "Savings"}
_FREQUENCY_LABELS = {
    RecurrenceFrequency.DAILY: "Daily",
    RecurrenceFrequency.WEEKLY: "Weekly",
    RecurrenceFrequency.MONTHLY: "Monthly",
    RecurrenceFrequency.YEARLY: "Yearly",
}
_BUCKET_LABELS = {
    ExpenseBucket.REPAIRS_AND_MAINTENANCE: "repairs and maintenance",
    ExpenseBucket.RECURRING_CHARGES: "recurring charges",
    ExpenseBucket.LOAN_REPAYMENTS: "loan repayments",
}


class SavingRunState(CodedEnum):
    """A decided run of a saving with a revenue rule; an undecided one has no row."""

    SAVED = 1
    SKIPPED = 2

    @property
    def label(self) -> str:
        return "Saved" if self is SavingRunState.SAVED else "Skipped"


class ConditionDays(IntEnum):
    """The days a saving's revenue rule measures: the run's day, its week or its month."""

    DAY = 1
    WEEK = 7
    MONTH = 30


class RunState(StrEnum):
    POSTED = "posted"
    SAVED = "saved"
    SKIPPED = "skipped"
    HELD = "held"


@dataclass(frozen=True, slots=True)
class PsvCompany:
    organization_id: UUID
    id: UUID
    name: str
    normalized_name: str
    archived_on: date | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Vehicle:
    organization_id: UUID
    id: UUID
    company_id: UUID
    registration: str
    joined_on: date
    left_on: date | None
    created_at: datetime
    updated_at: datetime
    fleet_number: str | None
    normalized_fleet_number: str | None
    initial_investment: Decimal | None


@dataclass(frozen=True, slots=True)
class VehicleTargetSet:
    """Seven day targets, Monday to Sunday, from ``starts_on`` until the next set starts;
    ``created_by`` is null for the sets made from the weekly targets."""

    organization_id: UUID
    id: UUID
    vehicle_id: UUID
    starts_on: date
    monday: Decimal
    tuesday: Decimal
    wednesday: Decimal
    thursday: Decimal
    friday: Decimal
    saturday: Decimal
    sunday: Decimal
    created_at: datetime
    created_by: UUID | None


@dataclass(frozen=True, slots=True)
class VehicleTarget:
    """The weekly targets before target sets; read by nothing, kept until the revenue
    migration drops them."""

    organization_id: UUID
    id: UUID
    vehicle_id: UUID
    revision: int
    effective_from: date
    weekly_amount: Decimal
    created_at: datetime


@dataclass(frozen=True, slots=True)
class VehicleAwayPeriod:
    """Away from ``left_on`` (inclusive) until ``returned_on`` (exclusive)."""

    organization_id: UUID
    id: UUID
    vehicle_id: UUID
    left_on: date
    returned_on: date
    created_at: datetime


@dataclass(frozen=True, slots=True)
class VehicleInvestment:
    organization_id: UUID
    id: UUID
    vehicle_id: UUID
    invested_on: date
    description: str
    amount: Decimal
    recorded_by: UUID
    recorded_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RecurringItem:
    organization_id: UUID
    id: UUID
    stopped_from: date | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RecurringSchedule:
    """When a version falls due: weekday (0 = Sunday) for weekly, month day or last day for
    monthly and yearly, plus the month for yearly."""

    frequency: RecurrenceFrequency
    day: int | None
    last_day: bool
    month: int | None


@dataclass(frozen=True, slots=True)
class RecurringAllocation:
    organization_id: UUID
    id: UUID
    version_id: UUID
    vehicle_id: UUID
    amount: Decimal


@dataclass(frozen=True, slots=True)
class RecurringVersion:
    organization_id: UUID
    id: UUID
    item_id: UUID
    revision: int
    effective_from: date
    name: str
    kind: RecurringKind
    amount: Decimal
    schedule: RecurringSchedule
    start_on: date
    end_on: date | None
    expense_item_id: UUID | None
    bucket: ExpenseBucket | None
    note: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ExpenseCategory:
    """``bucket`` is kept for the vehicle report and written by nothing; null for categories
    made since main categories."""

    organization_id: UUID
    id: UUID
    name: str
    normalized_name: str
    bucket: ExpenseBucket | None
    stopped_on: date | None
    created_at: datetime
    updated_at: datetime
    main_category_id: UUID | None


@dataclass(frozen=True, slots=True)
class ExpenseMainCategory:
    organization_id: UUID
    id: UUID
    name: str
    normalized_name: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ExpenseItem:
    organization_id: UUID
    id: UUID
    category_id: UUID
    name: str
    normalized_name: str
    stopped_on: date | None
    created_at: datetime
    updated_at: datetime


# --- what the setup routines answer ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompanySummary:
    id: UUID
    name: str
    vehicle_count: int
    active: bool
    archived_on: date | None


@dataclass(frozen=True, slots=True)
class CompanyPage:
    items: tuple[CompanySummary, ...]
    total: int


@dataclass(frozen=True, slots=True)
class CompanyChoice:
    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class TargetEntry:
    effective_from: date
    weekly_amount: Decimal
    revision: int


@dataclass(frozen=True, slots=True)
class AwayEntry:
    left_on: date
    returned_on: date


@dataclass(frozen=True, slots=True)
class NextTarget:
    starts_on: date
    day_targets: tuple[Decimal, ...]
    weekly_target: Decimal


@dataclass(frozen=True, slots=True)
class VehicleSummary:
    """``weekly_target``, ``recurring_items``, ``day_targets`` and ``next_target`` are null,
    and ``targets`` empty, for a caller without ``vehicles.view``; ``day_targets`` is also null
    when no set is in force today. ``targets`` is one entry per target set in the shape
    released clients read."""

    id: UUID
    company_id: UUID
    company_name: str
    registration: str
    joined_on: date
    left_on: date | None
    active: bool
    weekly_target: Decimal | None
    targets: tuple[TargetEntry, ...]
    recurring_items: int | None
    away: tuple[AwayEntry, ...]
    fleet_number: str | None
    initial_investment: Decimal | None
    day_targets: tuple[Decimal, ...] | None
    next_target: NextTarget | None


@dataclass(frozen=True, slots=True)
class TargetSetSummary:
    """``days`` Monday first; ``in_force`` for the set in force on the business date;
    ``can_remove`` when it has not started and the caller may set targets."""

    id: UUID
    starts_on: date
    days: tuple[Decimal, ...]
    week_total: Decimal
    in_force: bool
    can_remove: bool


@dataclass(frozen=True, slots=True)
class VehiclePage:
    items: tuple[VehicleSummary, ...]
    total: int


@dataclass(frozen=True, slots=True)
class Posting:
    """One due day of a scheduled item on the vehicle; ``bucket`` is null for a saving."""

    item_id: UUID
    version_id: UUID
    day: date
    name: str
    kind: RecurringKind
    amount: Decimal
    bucket: ExpenseBucket | None
    source: str | None


@dataclass(frozen=True, slots=True)
class VehicleReport:
    vehicle_id: UUID
    from_date: date
    through: date
    money_in: Decimal
    target: Decimal
    repairs: Decimal
    charges: Decimal
    loans: Decimal
    money_out: Decimal
    net: Decimal
    savings: Decimal
    after_savings: Decimal
    costs: Decimal
    postings: tuple[Posting, ...]


@dataclass(frozen=True, slots=True)
class ShareSummary:
    vehicle_id: UUID
    amount: Decimal
    registration: str
    active: bool


@dataclass(frozen=True, slots=True)
class RecurringSummary:
    """An item as its latest version, with the shares on vehicles the caller can see."""

    id: UUID
    version_id: UUID
    revision: int
    name: str
    kind: RecurringKind
    amount: Decimal
    frequency: RecurrenceFrequency
    day: int | None
    last_day: bool
    start_on: date
    end_on: date | None
    stopped_from: date | None
    allocations: tuple[ShareSummary, ...]
    partial: bool
    expense_item_id: UUID | None
    expense_item_name: str | None
    bucket: ExpenseBucket | None
    note: str | None
    month: int | None
    active_amount: Decimal
    paused_from: date | None
    last_run: date | None
    last_run_vehicles: int
    balance: Decimal | None
    last_run_states: RunStates | None
    condition: RevenueRule | None
    opening: OpeningSummary | None
    next_run: date | None


@dataclass(frozen=True, slots=True)
class RunStates:
    """The shares of a saving's last run date by state."""

    saved: int
    skipped: int
    held: int


@dataclass(frozen=True, slots=True)
class RevenueRule:
    """A saving's run is set aside only when the vehicle's revenue over ``days`` days reaches
    ``min``."""

    min: Decimal
    days: int


@dataclass(frozen=True, slots=True)
class OpeningSummary:
    """A saving's opening balance on the caller's vehicles."""

    date: date
    total: Decimal


@dataclass(frozen=True, slots=True)
class RecurringPage:
    items: tuple[RecurringSummary, ...]
    total: int


@dataclass(frozen=True, slots=True)
class RecurringRunShare:
    """A vehicle's share of one run: ``revenue`` is the decided figure, the window so far for
    a held share, None without a revenue rule."""

    vehicle_id: UUID
    registration: str
    amount: Decimal
    state: RunState
    revenue: Decimal | None


@dataclass(frozen=True, slots=True)
class RecurringRun:
    date: date
    amount: Decimal
    shares: tuple[RecurringRunShare, ...]


@dataclass(frozen=True, slots=True)
class RecurringRuns:
    """An item's runs on the caller's vehicles: the last ten run dates, newest first;
    ``total`` and the amounts count posted and saved shares only."""

    id: UUID
    name: str
    kind: RecurringKind
    start: date
    total: Decimal
    run_count: int
    runs: tuple[RecurringRun, ...]


@dataclass(frozen=True, slots=True)
class RecurringMonth:
    """The month holding the business date on the caller's vehicles; a figure of a kind the
    caller cannot view is None."""

    from_date: date
    to_date: date
    costs_due: Decimal | None
    saved: Decimal | None
    savings_balance: Decimal | None
    running_costs: int | None
    paused_costs: int | None
    running_savings: int | None
    paused_savings: int | None


@dataclass(frozen=True, slots=True)
class ShareVehicle:
    id: UUID
    company_id: UUID
    company_name: str
    registration: str
    active: bool
    fleet_number: str | None


@dataclass(frozen=True, slots=True)
class ExpenseItemSummary:
    id: UUID
    category_id: UUID
    name: str
    active: bool
    stopped_on: date | None


@dataclass(frozen=True, slots=True)
class ExpenseCategorySummary:
    id: UUID
    name: str
    bucket: ExpenseBucket | None
    active: bool
    stopped_on: date | None
    items: tuple[ExpenseItemSummary, ...]
    main_category_id: UUID | None
    main_category_name: str | None


@dataclass(frozen=True, slots=True)
class ExpenseCategoryPage:
    items: tuple[ExpenseCategorySummary, ...]
    total: int


@dataclass(frozen=True, slots=True)
class ExpenseItemChoice:
    id: UUID
    name: str
    category_id: UUID
    category_name: str
    bucket: ExpenseBucket | None
    main_category_id: UUID | None
    main_category_name: str | None


@dataclass(frozen=True, slots=True)
class MainCategorySummary:
    id: UUID
    name: str
    category_count: int
    item_count: int


@dataclass(frozen=True, slots=True)
class MainCategoryPage:
    items: tuple[MainCategorySummary, ...]
    total: int
    categories_without_main: int


@dataclass(frozen=True, slots=True)
class InvestmentEntry:
    id: UUID
    invested_on: date
    description: str
    amount: Decimal
    recorded_by: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class InvestmentSummary:
    """``returned`` is the vehicle's net from its join date through the business date;
    ``percent_paid_off`` is null when nothing went in."""

    vehicle_id: UUID
    total_invested: Decimal
    returned: Decimal
    percent_paid_off: Decimal | None
    entries: tuple[InvestmentEntry, ...]


# --- what the setup routines are told -----------------------------------------------------
# A field the caller may leave out is optional here: the routine refuses what is missing.


@dataclass(frozen=True, slots=True)
class SetupPageQuery:
    context: TenantContext
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class VehicleListQuery:
    """A page of vehicles, of one company when ``company_id`` is given."""

    context: TenantContext
    company_id: UUID | None
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class RecurringListQuery:
    """A page of scheduled items. ``kind`` and ``status`` are the request's text; the
    routine reads them (``cost`` or ``savings``, ``running`` or ``stopped``; blank or ``all``
    keeps every item)."""

    context: TenantContext
    kind: str | None
    company_id: UUID | None
    status: str | None
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class CompanySave:
    """A new company (``company_id`` None) or a rename."""

    context: TenantContext
    company_id: UUID | None
    name: str | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class CompanyLifecycle:
    context: TenantContext
    company_id: UUID
    reason: str | None


@dataclass(frozen=True, slots=True)
class VehicleDetails:
    """``day_targets`` is read on a new vehicle only; targets change through a target set."""

    company_id: UUID | None
    registration: str | None
    fleet_number: str | None
    joined_on: date | None
    day_targets: tuple[Decimal | None, ...] | None
    initial_investment: Decimal | None


@dataclass(frozen=True, slots=True)
class VehicleSave:
    """A new vehicle (``vehicle_id`` None) or an update."""

    context: TenantContext
    vehicle_id: UUID | None
    details: VehicleDetails
    reason: str | None


@dataclass(frozen=True, slots=True)
class VehicleRetirement:
    context: TenantContext
    vehicle_id: UUID
    left_on: date | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class VehicleReturn:
    """``returned_on`` None returns the vehicle on the business date."""

    context: TenantContext
    vehicle_id: UUID
    returned_on: date | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class VehicleReportQuery:
    """A ``period`` (``week`` or ``month``), or else both dates."""

    context: TenantContext
    vehicle_id: UUID
    period: str | None
    from_date: date | None
    through: date | None


@dataclass(frozen=True, slots=True)
class Share:
    vehicle_id: UUID | None
    amount: Decimal | None


@dataclass(frozen=True, slots=True)
class SavingCondition:
    """A saving's revenue rule as sent: set aside a run only when the revenue over ``days``
    days reaches ``min``; checked by the routine."""

    min: Decimal | None
    days: int | None


@dataclass(frozen=True, slots=True)
class OpeningAmount:
    vehicle_id: UUID | None
    amount: Decimal | None


@dataclass(frozen=True, slots=True)
class SavingOpening:
    """A saving's balance before its first run, per share vehicle, as at ``date``."""

    date: date | None
    amounts: tuple[OpeningAmount, ...]


@dataclass(frozen=True, slots=True)
class RecurringDefinition:
    """What a scheduled item save sends; ``kind``, ``frequency`` and ``month`` are the wire
    integers, checked by the routine. ``keep_opening`` (a revise that sent no opening) keeps
    the stored opening; otherwise ``opening`` replaces it, None removing it."""

    name: str | None
    kind: int
    amount: Decimal | None
    frequency: int
    day: int | None
    last_day: bool
    start: date | None
    end: date | None
    allocations: tuple[Share, ...]
    expense_item_id: UUID | None
    note: str | None
    month: int | None
    condition: SavingCondition | None = None
    opening: SavingOpening | None = None
    keep_opening: bool = False


@dataclass(frozen=True, slots=True)
class RecurringSave:
    """A new item (``item_id`` None) or a revision."""

    context: TenantContext
    item_id: UUID | None
    definition: RecurringDefinition
    reason: str | None


@dataclass(frozen=True, slots=True)
class RecurringPause:
    """A pause or a resume of an item, as of the business date."""

    context: TenantContext
    item_id: UUID


@dataclass(frozen=True, slots=True)
class RecurringRunsQuery:
    context: TenantContext
    item_id: UUID


@dataclass(frozen=True, slots=True)
class RecurringStop:
    context: TenantContext
    item_id: UUID
    confirmed: bool | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class RecurringCancelStop:
    context: TenantContext
    item_id: UUID


@dataclass(frozen=True, slots=True)
class ExpenseCategorySave:
    """A new category (``category_id`` None) or an update. On an update the main category
    changes only when ``main_category_given``; None is then "no main category"."""

    context: TenantContext
    category_id: UUID | None
    name: str | None
    main_category_id: UUID | None
    main_category_given: bool


@dataclass(frozen=True, slots=True)
class MainCategorySave:
    """A new main category (``main_category_id`` None) or a rename."""

    context: TenantContext
    main_category_id: UUID | None
    name: str | None


@dataclass(frozen=True, slots=True)
class ExpenseItemCreate:
    context: TenantContext
    category_id: UUID
    name: str | None


@dataclass(frozen=True, slots=True)
class ExpenseItemRename:
    context: TenantContext
    item_id: UUID
    name: str | None


@dataclass(frozen=True, slots=True)
class ExpenseLifecycle:
    """Turn a category or an item off (``stopped`` True) or on again."""

    context: TenantContext
    id: UUID
    stopped: bool


@dataclass(frozen=True, slots=True)
class VehicleQuery:
    context: TenantContext
    vehicle_id: UUID


@dataclass(frozen=True, slots=True)
class TargetSetSave:
    """``days`` Monday first, as sent; the routine refuses anything but seven amounts."""

    context: TenantContext
    vehicle_id: UUID
    starts_on: date | None
    days: tuple[Decimal | None, ...] | None


@dataclass(frozen=True, slots=True)
class TargetSetRemoval:
    context: TenantContext
    set_id: UUID


@dataclass(frozen=True, slots=True)
class InvestmentDetails:
    invested_on: date | None
    description: str | None
    amount: Decimal | None


@dataclass(frozen=True, slots=True)
class InvestmentCreate:
    context: TenantContext
    vehicle_id: UUID
    details: InvestmentDetails


@dataclass(frozen=True, slots=True)
class InvestmentUpdate:
    context: TenantContext
    entry_id: UUID
    details: InvestmentDetails


@dataclass(frozen=True, slots=True)
class InvestmentRemoval:
    context: TenantContext
    entry_id: UUID
