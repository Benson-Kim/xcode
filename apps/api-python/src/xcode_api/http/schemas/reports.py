"""Report contract models (``docs/06-http-contract.md`` 2.13.2): field order is the wire
order, names are the camelCase aliases of the fields unless an alias says otherwise. A cell
is a string, a JSON number or null; a money cell is a Decimal in the record and a number on
the wire, as every amount of the contract."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import Field, PlainSerializer

from ...domain.reports import CellKind
from .common import Amount, ApiModel


def _cell_to_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


Cell = Annotated[Any, PlainSerializer(_cell_to_json, return_type=Any, when_used="json")]


class ReportHolderDto(ApiModel):
    id: UUID
    name: str
    active: bool


class ReportsAccessDto(ApiModel):
    business_date: date
    first_day_of_week: int
    fleet: list[str]
    petty_cash: list[str]
    holders: list[ReportHolderDto]
    can_export: bool


class ReportFigureDto(ApiModel):
    label: str
    value: Amount
    kind: CellKind


class ReportColumnDto(ApiModel):
    key: str
    label: str
    kind: CellKind
    sum: bool


class ReportTableDto(ApiModel):
    """One page of a report; ``total`` and ``totals`` cover every row matching the search,
    the headline and figures the whole report."""

    group: str
    report: str
    title: str
    from_date: date | None = Field(alias="from")
    to_date: date | None = Field(alias="to")
    business_date: date
    headline: ReportFigureDto
    figures: list[ReportFigureDto]
    columns: list[ReportColumnDto]
    rows: list[list[Cell]]
    page_number: int
    page_size: int
    total: int
    totals: list[Amount | None]
