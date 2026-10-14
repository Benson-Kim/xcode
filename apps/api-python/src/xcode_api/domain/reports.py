"""Reports and exports vocabulary: the report groups, the cell kinds a client renders by, a
report table (one headline, a few figures, columns and rows the server builds and pages), the
reports catalogue, the queries, and what an export carries: the document a routine answers
(the table with every matching row plus the organization, period, filters and file name) and
the file an adapter builds from it.

Cells are strings, decimals, integers or null; dates travel as ``yyyy-MM-dd`` text. Nothing
here sums money: every figure, total and footer comes from the routine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from .tenancy import TenantContext


class ReportGroup(StrEnum):
    FLEET = "fleet"
    PETTYCASH = "pettycash"


class CellKind(StrEnum):
    """How a cell or figure reads: money and net are amounts (net shows below zero as bad), a
    date is ``yyyy-MM-dd``, count and quantity are plain numbers (quantity up to three
    decimals), percent is 0 to 100 with one decimal."""

    TEXT = "text"
    VEHICLE = "vehicle"
    DATE = "date"
    MONEY = "money"
    NET = "net"
    COUNT = "count"
    QUANTITY = "quantity"
    PERCENT = "percent"


class ExportFormat(StrEnum):
    XLSX = "xlsx"
    PDF = "pdf"


XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_CONTENT_TYPE = "application/pdf"
EXPORT_ROW_LIMIT = 10_000


@dataclass(frozen=True, slots=True)
class ReportFigure:
    label: str
    value: Decimal
    kind: CellKind


@dataclass(frozen=True, slots=True)
class ReportColumn:
    """``sum`` says the footer adds the column up over the rows shown."""

    key: str
    label: str
    kind: CellKind
    sum: bool


@dataclass(frozen=True, slots=True)
class ReportTable:
    """One page of a report: the rows matching the search, ``total`` the matching rows across
    every page, ``totals`` each summed column over all of them (null for the others); the
    headline and figures cover the whole report. ``from_date`` and ``to_date`` are null for an
    undated report."""

    group: str
    report: str
    title: str
    from_date: date | None
    to_date: date | None
    business_date: date
    headline: ReportFigure
    figures: tuple[ReportFigure, ...]
    columns: tuple[ReportColumn, ...]
    rows: tuple[tuple[Any, ...], ...]
    page_number: int
    page_size: int
    total: int
    totals: tuple[Decimal | None, ...]


@dataclass(frozen=True, slots=True)
class ReportHolder:
    id: UUID
    name: str
    active: bool


@dataclass(frozen=True, slots=True)
class ReportsAccess:
    """The reports the caller may open: the fleet and petty-cash report ids, the floats a
    petty-cash report can be cut to, and whether they may export."""

    business_date: date
    first_day_of_week: int
    fleet: tuple[str, ...]
    petty_cash: tuple[str, ...]
    holders: tuple[ReportHolder, ...]
    can_export: bool


@dataclass(frozen=True, slots=True)
class ReportDocument:
    """What a file needs, as the export routine answers it in the transaction that also
    writes the audit row: the table with every row the search left, its count and footer, and
    the organization, period, filters, exporter, instant, currency, file name and content type
    the adapters print."""

    group: str
    report: str
    title: str
    from_date: date | None
    to_date: date | None
    business_date: date
    headline: ReportFigure
    figures: tuple[ReportFigure, ...]
    columns: tuple[ReportColumn, ...]
    rows: tuple[tuple[Any, ...], ...]
    total: int
    totals: tuple[Decimal | None, ...]
    organization: str
    period: str | None
    filters: str | None
    exported_by: str
    exported_on: datetime
    currency: str | None
    file_name: str
    content_type: str


@dataclass(frozen=True, slots=True)
class ExportFile:
    """The bytes an adapter built from a document, with the name and type the answer carries."""

    content: bytes
    content_type: str
    file_name: str


@dataclass(frozen=True, slots=True)
class ReportQuery:
    context: TenantContext
    group: str
    report: str
    from_date: date | None
    to_date: date | None
    company_id: UUID | None
    holder_id: UUID | None
    q: str | None
    page: int | None
    page_size: int | None


@dataclass(frozen=True, slots=True)
class ReportExportQuery:
    """``format`` as the client sent it (null or blank is Excel)."""

    context: TenantContext
    group: str
    report: str
    from_date: date | None
    to_date: date | None
    company_id: UUID | None
    holder_id: UUID | None
    q: str | None
    format: str | None


@dataclass(frozen=True, slots=True)
class RevenueExportQuery:
    context: TenantContext
    week_start: date | None
    company_id: UUID | None
    format: str | None


@dataclass(frozen=True, slots=True)
class ExpenseExportQuery:
    context: TenantContext
    from_date: date | None
    to_date: date | None
    source: str | None
    q: str | None
    format: str | None


@dataclass(frozen=True, slots=True)
class PettyCashExportQuery:
    """``view`` is ``expenses`` or ``cash``; ``statuses`` the words the client sent."""

    context: TenantContext
    from_date: date | None
    to_date: date | None
    holder_id: UUID | None
    view: str | None
    statuses: tuple[str, ...] | None
    q: str | None
    format: str | None
