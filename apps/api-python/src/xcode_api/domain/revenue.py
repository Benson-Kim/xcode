"""Revenue vocabulary: the daily record, the no-earnings reasons, the grid cell statuses,
gap bands and dashboard periods; the week grid, the dashboard and the capture command with its
result.

``NoEarningsReason`` values are the code-table integers; ``label`` is the wire text and
``snapshot_name`` the name the change-log snapshots carry. ``tests/db/test_enum_parity.py``
proves code, name and label against ``revenue.no_earnings_reasons``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from .setup import CompanyChoice
from .tenancy import TenantContext
from .values import CodedEnum


class NoEarningsReason(CodedEnum):
    GARAGE = 1
    ARREST = 2
    NO_CREW = 3
    OTHER = 4

    @property
    def label(self) -> str:
        return _REASON_LABELS[self]

    @property
    def snapshot_name(self) -> str:
        return _REASON_SNAPSHOT_NAMES[self]


_REASON_LABELS = {
    NoEarningsReason.GARAGE: "Garage",
    NoEarningsReason.ARREST: "Arrest",
    NoEarningsReason.NO_CREW: "No Crew",
    NoEarningsReason.OTHER: "Other",
}
_REASON_SNAPSHOT_NAMES = {
    NoEarningsReason.GARAGE: "Garage",
    NoEarningsReason.ARREST: "Arrest",
    NoEarningsReason.NO_CREW: "NoCrew",
    NoEarningsReason.OTHER: "Other",
}


class CellStatus(StrEnum):
    """The state of one day in the revenue grid, in the words the wire and the clients use
    (``packages/shared/src/revenue.ts``, pinned by ``tests/unit/test_permission_keys.py``).
    """

    NONE = "none"
    FUTURE = "future"
    MISSING = "missing"
    AMOUNT = "amount"
    REASON = "reason"


class GapBand(StrEnum):
    """How far revenue is from the day targets that count so far: at or above them, below
    them by up to the organization's amber band, or further below."""

    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class DashboardPeriod(StrEnum):
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True, slots=True)
class RevenueRecord:
    """``revenue.records``: an amount, an amount with a reason (a day below the low-day
    threshold), or a reason alone (no revenue); a note only with ``OTHER``."""

    organization_id: UUID
    id: UUID
    vehicle_id: UUID
    business_date: date
    amount: Decimal | None
    reason: NoEarningsReason | None
    note: str | None
    captured_at: datetime
    captured_by: UUID
    updated_at: datetime
    updated_by: UUID
    corrected_after_date: bool
    version: int


@dataclass(frozen=True, slots=True)
class RevenueCell:
    """One day of a vehicle in the week grid: ``reason`` is the label, ``version`` is null
    without a record, and ``can_edit`` already weighs the caller's permissions."""

    day: date
    status: CellStatus
    expected: Decimal
    amount: Decimal | None
    reason: str | None
    note: str | None
    can_edit: bool
    edited_after_capture: bool
    version: int | None


@dataclass(frozen=True, slots=True)
class RevenueVehicleWeek:
    id: UUID
    company_id: UUID
    company_name: str
    registration: str
    joined_on: date
    left_on: date | None
    earliest_missing: date | None
    fleet_number: str | None
    days: tuple[RevenueCell, ...]
    total_amount: Decimal
    total_expected: Decimal
    percent: int | None
    gap: Decimal
    gap_band: GapBand | None
    below_threshold_days: int


@dataclass(frozen=True, slots=True)
class RevenueDayTotal:
    day: date
    amount: Decimal
    expected: Decimal


@dataclass(frozen=True, slots=True)
class RevenueGap:
    """Where capture starts: the earliest day still missing a record over the whole grid."""

    vehicle_id: UUID
    day: date


@dataclass(frozen=True, slots=True)
class RevenueWeek:
    """One page of the week grid. The totals, percent, gap, low and missing days, day totals
    and first gap cover the whole filtered grid, whichever page is listed; the threshold and the
    amber band are the organization's settings in force."""

    week_start: date
    week_through: date
    current_week_start: date
    business_date: date
    companies: tuple[CompanyChoice, ...]
    vehicles: tuple[RevenueVehicleWeek, ...]
    total_amount: Decimal
    total_expected: Decimal
    percent: int | None
    page_number: int
    page_size: int
    total_vehicles: int
    truncated: bool
    day_totals: tuple[RevenueDayTotal, ...]
    first_gap: RevenueGap | None
    low_day_threshold: Decimal
    gap_amber_percent: Decimal
    gap: Decimal
    gap_band: GapBand | None
    below_threshold_days: int
    missing_days: int


@dataclass(frozen=True, slots=True)
class RevenueDashboard:
    """The dashboard cards; a card the caller may not see is null."""

    period: DashboardPeriod
    from_date: date
    through: date
    business_date: date
    revenue: Decimal | None
    expected: Decimal | None
    percent: int | None
    captured_today: int | None
    vehicles_today: int | None
    missing_days: int | None
    missing_vehicles: int | None
    edited_records: int | None


@dataclass(frozen=True, slots=True)
class RevenueWeekQuery:
    """``week_start`` names its week (any day of it); ``vehicle_id`` asks for that vehicle in
    any week and is never paged; neither ``page`` nor ``page_size`` lists the first 500; ``q``
    matches a registration or fleet number."""

    context: TenantContext
    week_start: date | None
    company_id: UUID | None
    vehicle_id: UUID | None
    page: int | None
    page_size: int | None
    q: str | None


@dataclass(frozen=True, slots=True)
class RevenueDashboardQuery:
    """``period`` is the request's text (``today``, ``week``, ``month``); null means a week."""

    context: TenantContext
    period: str | None
    company_id: UUID | None


@dataclass(frozen=True, slots=True)
class RevenueCapture:
    """A day's revenue or no-earnings reason as the client sent it; ``reason`` is its text,
    ``expected_version`` the version of the record the client saw (null for a first capture) and
    ``captured_at`` when the client captured it (null: now)."""

    context: TenantContext
    vehicle_id: UUID
    day: date
    amount: Decimal | None
    reason: str | None
    note: str | None
    expected_version: int | None
    captured_at: datetime | None


class CaptureOutcome(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    REPLAYED = "replayed"


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """The record the capture left: its id and version, and whether it was created, updated
    or an identical entry replayed (nothing written)."""

    id: UUID
    version: int
    outcome: CaptureOutcome


@dataclass(frozen=True, slots=True)
class LastWeek:
    """The record seven days earlier: its amount and reason label."""

    amount: Decimal | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class RevenueDayVehicle:
    id: UUID
    company_id: UUID
    registration: str
    fleet_number: str | None
    day: RevenueCell
    last_week: LastWeek | None


@dataclass(frozen=True, slots=True)
class RevenueDay:
    """One day of the fleet for capture: at most 500 vehicles, ``truncated`` when more were in
    the fleet that day."""

    business_date: date
    date: date
    vehicles: tuple[RevenueDayVehicle, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class RevenueDayQuery:
    """``day`` null is the business date."""

    context: TenantContext
    day: date | None
    company_id: UUID | None


@dataclass(frozen=True, slots=True)
class RevenueDayRow:
    """One vehicle of a day save as the client sent it; checked by the routine."""

    vehicle_id: UUID | None
    amount: Decimal | None
    reason: str | None
    note: str | None
    version: int | None


@dataclass(frozen=True, slots=True)
class RevenueDaySave:
    context: TenantContext
    day: date
    rows: tuple[RevenueDayRow, ...]


@dataclass(frozen=True, slots=True)
class RevenueDaySaved:
    vehicle_id: UUID
    id: UUID
    version: int


@dataclass(frozen=True, slots=True)
class RevenueDayResult:
    """Each saved row in the order sent."""

    rows: tuple[RevenueDaySaved, ...]
