"""Revenue week grid, dashboard and capture contract models
(``docs/inventory/inventory-http-contract.md`` section 2.10): field order is the wire order,
names are the camelCase aliases of the fields unless an alias says otherwise.

The capture body's fields default to null, and the routine refuses what is missing with its
own sentence; the amount is read exactly and checked by the routine, so a third decimal place
gets the money sentence, not a binding error. ``capturedAt`` must carry its offset. Properties
added since the released clients come last in each model."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import AwareDatetime, Field

from ...domain.revenue import CellStatus, DashboardPeriod, GapBand
from .common import Amount, ApiModel, Money


class RevenueCellDto(ApiModel):
    """One day of a vehicle; also the ``current`` member of the 409 for a stale version."""

    day: date = Field(alias="date")
    status: CellStatus
    expected: Money
    amount: Money | None
    reason: str | None
    note: str | None
    can_edit: bool
    edited_after_capture: bool
    version: int | None


class RevenueVehicleDto(ApiModel):
    id: UUID
    company_id: UUID
    company_name: str
    registration: str
    joined_on: date
    left_on: date | None
    earliest_missing: date | None
    days: list[RevenueCellDto]
    total_amount: Money
    total_expected: Money
    percent: int | None
    fleet_number: str | None
    gap: Money
    gap_band: GapBand | None
    below_threshold_days: int


class RevenueCompanyOption(ApiModel):
    id: UUID
    name: str


class RevenueDayTotalDto(ApiModel):
    day: date = Field(alias="date")
    amount: Money
    expected: Money


class RevenueGapDto(ApiModel):
    vehicle_id: UUID
    day: date = Field(alias="date")


class RevenueWeekDto(ApiModel):
    """One page of the grid; the totals, percent, day totals, first gap, gap, low days and
    missing days cover all of it."""

    week_start: date
    week_through: date
    current_week_start: date
    business_date: date
    companies: list[RevenueCompanyOption]
    vehicles: list[RevenueVehicleDto]
    total_amount: Money
    total_expected: Money
    percent: int | None
    page_number: int
    page_size: int
    total_vehicles: int
    truncated: bool
    day_totals: list[RevenueDayTotalDto]
    first_gap: RevenueGapDto | None
    low_day_threshold: Money
    gap_amber_percent: Money
    gap: Money
    gap_band: GapBand | None
    below_threshold_days: int
    missing_days: int


class RevenueDashboardDto(ApiModel):
    """A card the caller may not see is null."""

    period: DashboardPeriod
    from_date: date = Field(alias="from")
    through: date
    business_date: date
    revenue: Money | None
    expected: Money | None
    percent: int | None
    captured_today: int | None
    vehicles_today: int | None
    missing_days: int | None
    missing_vehicles: int | None
    edited_records: int | None


class SaveRevenue(ApiModel):
    """``version`` is the version of the record the client saw, null for a first capture;
    ``capturedAt`` when the client captured the entry (absent: now), which the back-dating limit
    is checked at, held to the last 72 hours."""

    amount: Amount | None = None
    reason: str | None = None
    note: str | None = None
    version: int | None = Field(default=None, ge=-(2**63), le=2**63 - 1)
    captured_at: AwareDatetime | None = None


class RevenueSaved(ApiModel):
    id: UUID
    version: int


class LastWeekDto(ApiModel):
    amount: Money | None
    reason: str | None


class RevenueDayVehicleDto(ApiModel):
    id: UUID
    company_id: UUID
    registration: str
    day: RevenueCellDto
    last_week: LastWeekDto | None
    fleet_number: str | None


class RevenueDayDto(ApiModel):
    """``GET /setup/revenue/day``: at most 500 vehicles, ``truncated`` when more."""

    day: date = Field(alias="date")
    business_date: date
    vehicles: list[RevenueDayVehicleDto]
    truncated: bool


class SaveRevenueDayRow(ApiModel):
    """A row of ``PUT /setup/revenue/day/{date}``, read as ``SaveRevenue`` reads its body."""

    vehicle_id: UUID | None = None
    amount: Amount | None = None
    reason: str | None = None
    note: str | None = None
    version: int | None = Field(default=None, ge=-(2**63), le=2**63 - 1)


class SaveRevenueDay(ApiModel):
    rows: list[SaveRevenueDayRow] = Field(default_factory=list)


class RevenueDayRowSaved(ApiModel):
    vehicle_id: UUID
    id: UUID
    version: int


class RevenueDaySaved(ApiModel):
    """Each saved row in the order sent."""

    rows: list[RevenueDayRowSaved]
