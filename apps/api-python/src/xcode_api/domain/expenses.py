"""Central-expense vocabulary: the ledger's sources and rows, the form's options, and the
commands on a purchase and its rows with their answers.

A purchase for one to fifty vehicles is stored as one row per vehicle sharing the purchase (its
group); the ledger also lists approved petty-cash expenses and scheduled cost runs, which are
read there and never changed. Every rule lives in the ``57_expenses`` routines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from .setup import ExpenseBucket
from .tenancy import TenantContext


class ExpenseSource(StrEnum):
    CENTRAL = "central"
    PETTY_CASH = "pettycash"
    SCHEDULED = "scheduled"


@dataclass(frozen=True, slots=True)
class ExpensePermissions:
    can_record: bool
    can_correct: bool


@dataclass(frozen=True, slots=True)
class ExpenseFigures:
    """The whole period by source, whatever the source filter and the search say."""

    total: Decimal
    central: Decimal
    petty_cash: Decimal
    scheduled: Decimal


@dataclass(frozen=True, slots=True)
class ExpenseGroup:
    """The purchase a row came from when several vehicles shared it, as bought."""

    id: UUID
    size: int
    total: Decimal
    units: Decimal
    unit_amount: Decimal


@dataclass(frozen=True, slots=True)
class ExpenseLedgerRow:
    """One ledger row; also the ``current`` member of a 409. ``id`` is a scheduled run's
    ``{item}:{yyyy-MM-dd}:{vehicle}``; ``version`` belongs to central rows only."""

    id: str
    source: ExpenseSource
    entry_date: date
    vehicle_id: UUID
    registration: str
    expense_item_id: UUID | None
    item_name: str
    category_name: str | None
    bucket: ExpenseBucket
    units: Decimal
    unit_amount: Decimal
    total: Decimal
    note: str | None
    recorded_by_name: str | None
    holder_name: str | None
    schedule_id: UUID | None
    group: ExpenseGroup | None
    version: int | None
    can_edit: bool
    can_remove: bool
    main_category_name: str | None
    fleet_number: str | None


@dataclass(frozen=True, slots=True)
class ExpenseLedger:
    """One page; ``total`` and ``amount`` count every row matching the source and search."""

    business_date: date
    from_date: date
    to_date: date
    permissions: ExpensePermissions
    figures: ExpenseFigures
    items: tuple[ExpenseLedgerRow, ...]
    page_number: int
    page_size: int
    total: int
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ExpenseVehicleOption:
    id: UUID
    company_id: UUID
    company_name: str
    registration: str
    active: bool
    fleet_number: str | None


@dataclass(frozen=True, slots=True)
class ExpenseItemOption:
    id: UUID
    name: str
    category_id: UUID
    category_name: str
    bucket: ExpenseBucket
    main_category_name: str | None


@dataclass(frozen=True, slots=True)
class ExpenseOptions:
    vehicles: tuple[ExpenseVehicleOption, ...]
    items: tuple[ExpenseItemOption, ...]


@dataclass(frozen=True, slots=True)
class ExpenseAllocation:
    """One vehicle's part of a purchase, as the client sent it."""

    vehicle_id: UUID | None
    amount: Decimal | None


@dataclass(frozen=True, slots=True)
class ExpensePurchase:
    """``id`` is the client's purchase id (null to let the server choose); sending it again
    answers the rows the first save made."""

    context: TenantContext
    id: UUID | None
    day: date | None
    expense_item_id: UUID | None
    units: Decimal | None
    unit_amount: Decimal | None
    note: str | None
    allocations: tuple[ExpenseAllocation, ...] | None


@dataclass(frozen=True, slots=True)
class ExpenseChange:
    context: TenantContext
    entry_id: UUID
    day: date | None
    vehicle_id: UUID | None
    expense_item_id: UUID | None
    units: Decimal | None
    unit_amount: Decimal | None
    note: str | None
    expected_version: int | None


@dataclass(frozen=True, slots=True)
class ExpenseRemoval:
    context: TenantContext
    entry_id: UUID
    expected_version: int | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class ExpenseRecorded:
    """The purchase's rows (in the order sent; by id for a retried purchase) and its total."""

    ids: tuple[UUID, ...]
    total: Decimal


@dataclass(frozen=True, slots=True)
class ExpenseSaved:
    id: UUID
    version: int


@dataclass(frozen=True, slots=True)
class ExpenseLedgerQuery:
    context: TenantContext
    from_date: date | None
    to_date: date | None
    source: str | None
    q: str | None
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class ExpenseOptionsQuery:
    context: TenantContext
    day: date | None
