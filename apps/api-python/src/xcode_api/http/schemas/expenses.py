"""Central-expense contract models (``docs/06-http-contract.md`` section 2.13.1): field order
is the wire order, names are the camelCase aliases of the fields unless an alias says
otherwise; what Python adds to .NET's shapes comes last.

Body fields default to null and the routines refuse what is missing with their own
sentences; amounts and units are read exactly and checked by the routine, so a third decimal
place gets the expense sentence, not a binding error."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import Field

from ...domain.expenses import ExpenseSource
from ...domain.setup import ExpenseBucket
from .common import Amount, ApiModel, Money

Version = Annotated[int | None, Field(ge=-(2**63), le=2**63 - 1)]


class ExpenseAllocationBody(ApiModel):
    vehicle_id: UUID | None = None
    amount: Amount | None = None


class RecordExpense(ApiModel):
    """``id`` is the client's purchase id (sending it again answers the rows it made)."""

    id: UUID | None = None
    entry_date: date | None = Field(default=None, alias="date")
    expense_item_id: UUID | None = None
    units: Amount | None = None
    unit_amount: Amount | None = None
    note: str | None = None
    allocations: list[ExpenseAllocationBody] | None = None


class ChangeExpense(ApiModel):
    entry_date: date | None = Field(default=None, alias="date")
    vehicle_id: UUID | None = None
    expense_item_id: UUID | None = None
    units: Amount | None = None
    unit_amount: Amount | None = None
    note: str | None = None
    version: Version = None


class RemoveExpense(ApiModel):
    version: Version = None
    reason: str | None = None


class ExpenseRecordedDto(ApiModel):
    ids: list[UUID]
    total: Money


class ExpenseSavedDto(ApiModel):
    id: UUID
    version: int


class ExpensePermissionsDto(ApiModel):
    can_record: bool
    can_correct: bool


class ExpenseFiguresDto(ApiModel):
    total: Money
    central: Money
    petty_cash: Money
    scheduled: Money


class ExpenseGroupDto(ApiModel):
    id: UUID
    size: int
    total: Money
    units: Amount
    unit_amount: Money


class ExpenseLedgerRowDto(ApiModel):
    """One ledger row; also the ``current`` member of a 409."""

    id: str
    source: ExpenseSource
    entry_date: date = Field(alias="date")
    vehicle_id: UUID
    registration: str
    expense_item_id: UUID | None
    item_name: str
    category_name: str | None
    bucket: ExpenseBucket
    units: Amount
    unit_amount: Money
    total: Money
    note: str | None
    recorded_by_name: str | None
    holder_name: str | None
    schedule_id: UUID | None
    group: ExpenseGroupDto | None
    version: int | None
    can_edit: bool
    can_remove: bool
    main_category_name: str | None
    fleet_number: str | None


class ExpenseLedgerDto(ApiModel):
    business_date: date
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    permissions: ExpensePermissionsDto
    figures: ExpenseFiguresDto
    items: list[ExpenseLedgerRowDto]
    page_number: int
    page_size: int
    total: int
    amount: Money


class ExpenseVehicleOptionDto(ApiModel):
    id: UUID
    company_id: UUID
    company_name: str
    registration: str
    active: bool
    fleet_number: str | None


class ExpenseItemOptionDto(ApiModel):
    id: UUID
    name: str
    category_id: UUID
    category_name: str
    bucket: ExpenseBucket
    main_category_name: str | None


class ExpenseOptionsDto(ApiModel):
    vehicles: list[ExpenseVehicleOptionDto]
    items: list[ExpenseItemOptionDto]
