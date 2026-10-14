"""Petty-cash vocabulary: entry kinds and statuses, the wire words of an entry's state, the
overview, list, options and dashboard documents, and the commands with their answers.

``PettyCashKind`` and ``PettyCashStatus`` values are the code-table integers; their wire form
is the lower-case name (``EntryKind``, ``EntryState``), and ``snapshot_name`` is the name the
change-log snapshots carry. ``tests/db/test_enum_parity.py`` proves code, name and label
against ``pettycash.kinds`` and ``pettycash.statuses``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from .expenses import ExpenseAllocation
from .setup import ExpenseBucket
from .tenancy import TenantContext
from .values import CodedEnum


class PettyCashKind(CodedEnum):
    CASH = 1
    EXPENSE = 2
    CREDIT = 3

    @property
    def label(self) -> str:
        return _KIND_LABELS[self]

    @property
    def snapshot_name(self) -> str:
        return self.name.capitalize()


_KIND_LABELS = {
    PettyCashKind.CASH: "Cash given",
    PettyCashKind.EXPENSE: "Expense",
    PettyCashKind.CREDIT: "Credit note",
}


class PettyCashStatus(CodedEnum):
    """Only expenses have one; 3 was the .NET ``SentBack`` and stays unused."""

    WAITING = 1
    APPROVED = 2
    REJECTED = 4

    @property
    def label(self) -> str:
        return self.name.capitalize()

    @property
    def snapshot_name(self) -> str:
        return self.name.capitalize()


class EntryKind(StrEnum):
    CASH = "cash"
    EXPENSE = "expense"
    CREDIT = "credit"


class EntryState(StrEnum):
    """The status word on the wire: a waiting expense with a sent-back note is sent back."""

    WAITING = "waiting"
    SENT_BACK = "sentBack"
    APPROVED = "approved"
    REJECTED = "rejected"


class OverviewPeriod(StrEnum):
    DAY = "day"
    WEEK = "week"
    RANGE = "range"


class SaveOutcome(StrEnum):
    """``created`` by a create, ``saved`` by any other write, ``replayed`` when nothing was
    written because the same request had already been applied."""

    CREATED = "created"
    SAVED = "saved"
    REPLAYED = "replayed"


@dataclass(frozen=True, slots=True)
class PettyCashPermissions:
    """The caller's petty-cash rights; ``holder_id`` is the caller when they keep a float,
    ``earliest_date`` the back-dating limit (null for none)."""

    holder_id: UUID | None
    can_spend: bool
    can_view_all: bool
    can_issue: bool
    can_issue_negative: bool
    can_approve_item: bool
    can_approve_day: bool
    approval_limit: Decimal | None
    can_view: bool
    can_spend_other: bool
    can_edit_own: bool
    can_edit: bool
    can_delete_own: bool
    can_delete: bool
    can_delete_approved: bool
    can_send_back: bool
    can_reject: bool
    can_reopen: bool
    can_credit: bool
    can_delete_cash: bool
    earliest_date: date | None


@dataclass(frozen=True, slots=True)
class PettyCashHolder:
    """A float: ``active`` while its keeper holds ``pettycash.spend``, else kept for its
    entries."""

    id: UUID
    name: str
    active: bool


@dataclass(frozen=True, slots=True)
class PettyCashFigures:
    """The chosen days of the chosen floats; rejected expenses count in none of them."""

    opening_balance: Decimal
    cash_received: Decimal
    expenses: Decimal
    credit_notes: Decimal
    money_out: Decimal
    closing_balance: Decimal
    waiting: Decimal
    waiting_count: int


@dataclass(frozen=True, slots=True)
class PettyCashFloat:
    """One float over all its entries the caller may see."""

    holder_id: UUID
    name: str
    active: bool
    cash_received: Decimal
    credit_notes: Decimal
    expenses: Decimal
    waiting: Decimal
    waiting_count: int
    approved: Decimal
    sent_back: Decimal
    balance: Decimal
    last_cash_on: date | None
    rejected: Decimal


@dataclass(frozen=True, slots=True)
class PettyCashOverview:
    business_date: date
    day: date
    period: OverviewPeriod
    from_date: date
    to_date: date
    permissions: PettyCashPermissions
    holders: tuple[PettyCashHolder, ...]
    figures: PettyCashFigures
    floats: tuple[PettyCashFloat, ...]


@dataclass(frozen=True, slots=True)
class PettyCashEntry:
    """One entry as the list and a 409's ``current`` serve it, with the caller's actions on
    it. ``holder_name`` and ``recorded_by_name`` are empty for a missing member;
    ``registration``, ``expense_item_name`` and ``bucket`` belong to expenses."""

    id: UUID
    kind: EntryKind
    holder_id: UUID
    holder_name: str
    entry_date: date
    vehicle_id: UUID | None
    registration: str | None
    expense_item_id: UUID | None
    expense_item_name: str | None
    bucket: ExpenseBucket | None
    units: Decimal
    unit_amount: Decimal
    total: Decimal
    payee: str | None
    note: str | None
    reimbursable: bool
    status: EntryState | None
    sent_back_note: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    recorded_by_name: str
    recorded_at: datetime
    updated_at: datetime
    version: int
    can_edit: bool
    can_remove: bool
    can_review: bool
    above_limit: bool
    reject_reason: str | None
    reopen_reason: str | None
    can_send_back: bool
    can_reject: bool
    can_reopen: bool
    group: PettyCashGroup | None = None


@dataclass(frozen=True, slots=True)
class PettyCashGroup:
    """The shared purchase an expense is part of: ``size`` counts its parts not removed and
    not rejected now; the rest is the purchase as bought."""

    id: UUID
    size: int
    total: Decimal
    units: Decimal
    unit_amount: Decimal


@dataclass(frozen=True, slots=True)
class PettyCashEntryPage:
    items: tuple[PettyCashEntry, ...]
    total: int


@dataclass(frozen=True, slots=True)
class PettyCashVehicleOption:
    id: UUID
    company_id: UUID
    company_name: str
    registration: str
    active: bool
    fleet_number: str | None = None


@dataclass(frozen=True, slots=True)
class PettyCashItemOption:
    id: UUID
    name: str
    category_id: UUID
    category_name: str
    bucket: ExpenseBucket | None


@dataclass(frozen=True, slots=True)
class PettyCashOptions:
    """What an entry form offers on its date: vehicles and items for a caller who records or
    edits expenses, active floats for one who records for others, gives cash or credit notes.
    """

    vehicles: tuple[PettyCashVehicleOption, ...]
    items: tuple[PettyCashItemOption, ...]
    holders: tuple[PettyCashHolder, ...]


@dataclass(frozen=True, slots=True)
class PettyCashFloatCard:
    balance: Decimal
    waiting_count: int
    waiting_total: Decimal
    sent_back_count: int
    approved_this_month: Decimal


@dataclass(frozen=True, slots=True)
class PettyCashApprovalHolder:
    holder_id: UUID
    name: str
    count: int
    total: Decimal
    oldest: date


@dataclass(frozen=True, slots=True)
class PettyCashApprovalsCard:
    count: int
    total: Decimal
    approval_limit: Decimal | None
    above_limit: int
    holders: tuple[PettyCashApprovalHolder, ...]


@dataclass(frozen=True, slots=True)
class PettyCashDashboard:
    """The caller's float card (with ``pettycash.spend``) and approvals card (with
    ``pettycash.approve_item``); a card the caller may not see is null."""

    float_card: PettyCashFloatCard | None
    approvals: PettyCashApprovalsCard | None


@dataclass(frozen=True, slots=True)
class PettyCashSaved:
    """The entry a write left, the float's balance after it, and what happened."""

    id: UUID
    version: int
    status: EntryState | None
    balance: Decimal
    outcome: SaveOutcome


@dataclass(frozen=True, slots=True)
class PettyCashApproved:
    """``total`` is the signed sum of the approved entries; ``skipped`` the rest asked for."""

    approved: int
    total: Decimal
    skipped: int


@dataclass(frozen=True, slots=True)
class PettyCashOverviewQuery:
    """With ``from_date`` or ``to_date`` the days are that period; else ``date`` (null for
    today) and ``period`` (``day`` or ``week``, as the client sent it)."""

    context: TenantContext
    day: date | None
    period: str | None
    holder_id: UUID | None
    from_date: date | None
    to_date: date | None


@dataclass(frozen=True, slots=True)
class PettyCashEntryQuery:
    """``kinds`` and ``statuses`` are the words the client sent (null or empty for all)."""

    context: TenantContext
    from_date: date | None
    to_date: date | None
    holder_id: UUID | None
    kinds: tuple[str, ...] | None
    statuses: tuple[str, ...] | None
    q: str | None
    page: int | None
    page_size: int | None


@dataclass(frozen=True, slots=True)
class PettyCashOptionsQuery:
    context: TenantContext
    day: date | None


@dataclass(frozen=True, slots=True)
class PettyCashLine:
    """An entry as the client sent it; ``kind`` is its text, ``units`` null for one."""

    kind: str | None
    day: date | None
    unit_amount: Decimal | None
    holder_id: UUID | None
    vehicle_id: UUID | None
    expense_item_id: UUID | None
    units: Decimal | None
    payee: str | None
    note: str | None
    reimbursable: bool


@dataclass(frozen=True, slots=True)
class PettyCashCreate:
    """``id`` is the client's id for the entry (null to let the server choose); sending it
    again replays the first save. An expense bought for several vehicles carries
    ``allocations``: one entry per vehicle, the first one under ``id``."""

    context: TenantContext
    id: UUID | None
    line: PettyCashLine
    allocations: tuple[ExpenseAllocation, ...] | None = None


@dataclass(frozen=True, slots=True)
class PettyCashUpdate:
    context: TenantContext
    entry_id: UUID
    line: PettyCashLine
    expected_version: int | None


@dataclass(frozen=True, slots=True)
class PettyCashDecision:
    """Approve, send back (``text`` the comment), reject, reopen or remove (``text`` the
    reason) one entry at the version the client saw."""

    context: TenantContext
    entry_id: UUID
    expected_version: int | None
    text: str | None


@dataclass(frozen=True, slots=True)
class PettyCashDayApproval:
    """``date`` alone is one day; with ``to`` the days ``date`` to ``to``."""

    context: TenantContext
    day: date | None
    to: date | None
    holder_id: UUID | None


@dataclass(frozen=True, slots=True)
class PettyCashTicked:
    id: UUID
    version: int | None


@dataclass(frozen=True, slots=True)
class PettyCashEntriesApproval:
    context: TenantContext
    entries: tuple[PettyCashTicked, ...]
