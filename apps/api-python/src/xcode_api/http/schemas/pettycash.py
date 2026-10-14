"""Petty-cash contract models (``docs/06-http-contract.md`` section 2.11): field order is the
wire order, names are the camelCase aliases of the fields unless an alias says otherwise.

Body fields default to null and the routines refuse what is missing with their own
sentences; amounts and units are read exactly and checked by the routine, so a third decimal
place gets the petty-cash sentence, not a binding error."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import Field

from ...domain.pettycash import EntryKind, EntryState, OverviewPeriod
from ...domain.setup import ExpenseBucket
from .common import Amount, ApiModel, Instant, Money
from .expenses import ExpenseAllocationBody

Version = Annotated[int | None, Field(ge=-(2**63), le=2**63 - 1)]


class SavePettyCashEntry(ApiModel):
    """``id`` is the client's id for a new entry (sending it again replays the first save);
    ``units`` absent is one; ``version`` is the version the client saw (updates only);
    ``allocations`` share an expense between vehicles (creates only)."""

    kind: str | None = None
    entry_date: date | None = Field(default=None, alias="date")
    unit_amount: Amount | None = None
    id: UUID | None = None
    holder_id: UUID | None = None
    vehicle_id: UUID | None = None
    expense_item_id: UUID | None = None
    units: Amount | None = None
    payee: str | None = None
    note: str | None = None
    reimbursable: bool = False
    version: Version = None
    allocations: list[ExpenseAllocationBody] | None = None


class ReviewPettyCashEntry(ApiModel):
    version: Version = None


class SendBackPettyCashEntry(ApiModel):
    version: Version = None
    comment: str | None = None


class RemovePettyCashEntry(ApiModel):
    version: Version = None
    reason: str | None = None


class DecidePettyCashEntry(ApiModel):
    version: Version = None
    reason: str | None = None


class ApprovePettyCashDay(ApiModel):
    day: date | None = Field(default=None, alias="date")
    holder_id: UUID | None = None
    to: date | None = None


class TickedPettyCashEntry(ApiModel):
    id: UUID
    version: Version = None


class ApprovePettyCashEntries(ApiModel):
    """A null list asks for the entries as an empty one does (the routine says so)."""

    entries: list[TickedPettyCashEntry] | None = None


class PettyCashSaved(ApiModel):
    id: UUID
    version: int
    status: EntryState | None
    balance: Money


class PettyCashDayApproved(ApiModel):
    approved: int
    total: Money
    skipped: int


class PettyCashPermissionsDto(ApiModel):
    holder_id: UUID | None
    can_spend: bool
    can_view_all: bool
    can_issue: bool
    can_issue_negative: bool
    can_approve_item: bool
    can_approve_day: bool
    approval_limit: Amount | None
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


class PettyCashHolderDto(ApiModel):
    id: UUID
    name: str
    active: bool


class PettyCashFiguresDto(ApiModel):
    opening_balance: Money
    cash_received: Money
    expenses: Money
    credit_notes: Money
    money_out: Money
    closing_balance: Money
    waiting: Money
    waiting_count: int


class PettyCashFloatDto(ApiModel):
    holder_id: UUID
    name: str
    active: bool
    cash_received: Money
    credit_notes: Money
    expenses: Money
    waiting: Money
    waiting_count: int
    approved: Money
    sent_back: Money
    balance: Money
    last_cash_on: date | None
    rejected: Money


class PettyCashOverviewDto(ApiModel):
    business_date: date
    day: date = Field(alias="date")
    period: OverviewPeriod
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    permissions: PettyCashPermissionsDto
    holders: list[PettyCashHolderDto]
    figures: PettyCashFiguresDto
    floats: list[PettyCashFloatDto]


class PettyCashGroupDto(ApiModel):
    id: UUID
    size: int
    total: Money
    units: Amount
    unit_amount: Money


class PettyCashEntryDto(ApiModel):
    """One entry; also the ``current`` member of a 409."""

    id: UUID
    kind: EntryKind
    holder_id: UUID
    holder_name: str
    entry_date: date = Field(alias="date")
    vehicle_id: UUID | None
    registration: str | None
    expense_item_id: UUID | None
    expense_item_name: str | None
    bucket: ExpenseBucket | None
    units: Amount
    unit_amount: Money
    total: Money
    payee: str | None
    note: str | None
    reimbursable: bool
    status: EntryState | None
    sent_back_note: str | None
    reviewed_by_name: str | None
    reviewed_at: Instant | None
    recorded_by_name: str
    recorded_at: Instant
    updated_at: Instant
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
    group: PettyCashGroupDto | None = None


class PettyCashVehicleOptionDto(ApiModel):
    id: UUID
    company_id: UUID
    company_name: str
    registration: str
    active: bool
    fleet_number: str | None = None


class PettyCashItemOptionDto(ApiModel):
    id: UUID
    name: str
    category_id: UUID
    category_name: str
    bucket: ExpenseBucket | None


class PettyCashOptionsDto(ApiModel):
    vehicles: list[PettyCashVehicleOptionDto]
    items: list[PettyCashItemOptionDto]
    holders: list[PettyCashHolderDto]


class PettyCashFloatCardDto(ApiModel):
    balance: Money
    waiting_count: int
    waiting_total: Money
    sent_back_count: int
    approved_this_month: Money


class PettyCashApprovalHolderDto(ApiModel):
    holder_id: UUID
    name: str
    count: int
    total: Money
    oldest: date


class PettyCashApprovalsCardDto(ApiModel):
    count: int
    total: Money
    approval_limit: Amount | None
    above_limit: int
    holders: list[PettyCashApprovalHolderDto]


class PettyCashDashboardDto(ApiModel):
    """A card the caller may not see is null."""

    float_card: PettyCashFloatCardDto | None = Field(alias="float")
    approvals: PettyCashApprovalsCardDto | None
