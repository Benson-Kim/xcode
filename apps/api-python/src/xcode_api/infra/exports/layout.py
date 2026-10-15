"""What both export adapters share: the sheet and file words of a document (period, stamp,
figure labels), the cell texts a PDF prints, and the characters a file must not carry."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from ...domain.reports import CellKind, ReportDocument, ReportFigure

BRAND = "XCODE Fleet finance"
EMPTY_WORDS = "Nothing to show for these dates."
_ILLEGAL_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_SHEET_FORBIDDEN = re.compile(r"[:\\/?*\[\]]")
_FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def clean(text: str) -> str:
    """The text without the characters XML cannot hold."""
    return _ILLEGAL_XML.sub("", text)


def looks_like_formula(text: str) -> bool:
    return text.startswith(_FORMULA_LEADS)


def sheet_name(title: str) -> str:
    """At most 31 characters, none of ``: \\ / ? * [ ]``; never empty."""
    name = _SHEET_FORBIDDEN.sub("", clean(title)).strip()[:31].strip()
    return name or "Report"


def day_words(day: date) -> str:
    """``d MMM yyyy`` with the invariant month abbreviations (``9 Oct 2026``)."""
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year}"


def exported_day(document: ReportDocument) -> date:
    return document.exported_on.astimezone(UTC).date()


def period_words(document: ReportDocument) -> str:
    """The document's period, or ``As at {d MMM yyyy}`` for an undated report."""
    return document.period or f"As at {day_words(exported_day(document))}"


def subtitle(document: ReportDocument) -> str:
    parts = [document.organization, period_words(document)]
    if document.filters:
        parts.append(document.filters)
    return "  ·  ".join(parts)


def stamp(document: ReportDocument) -> str:
    return f"Exported {day_words(exported_day(document))} by {document.exported_by}"


def figure_label(figure: ReportFigure, currency: str | None) -> str:
    """The label upper-cased, with the currency after a money or net figure."""
    label = figure.label.upper()
    if currency and figure.kind in (CellKind.MONEY, CellKind.NET):
        label = f"{label} ({currency})"
    return label


def footer_words(document: ReportDocument) -> str:
    return f"{BRAND} | {document.title}, {period_words(document)}"


def rows_words(count: int) -> str:
    return "1 row" if count == 1 else f"{count} rows"


def parse_date(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def number_text(value: Decimal | int | float, kind: CellKind) -> str:
    """How a PDF prints a number of a kind: money with two decimals and separators, counts
    whole, quantities up to three decimals, percents with one decimal and the sign."""
    amount = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    if kind in (CellKind.MONEY, CellKind.NET):
        return f"{amount:,.2f}"
    if kind == CellKind.COUNT:
        return f"{int(amount):,}"
    if kind == CellKind.PERCENT:
        return f"{amount:.1f}%"
    if kind == CellKind.QUANTITY:
        return f"{amount:,.3f}".rstrip("0").rstrip(".")
    return f"{amount:,}" if amount == amount.to_integral_value() else f"{amount:,.2f}"


def cell_words(cell: Any, kind: CellKind) -> str:
    """What a PDF prints in a cell: a date as ``d MMM yyyy``, a number by its kind, a text as
    is (cleaned), nothing for null."""
    if cell is None:
        return ""
    if isinstance(cell, bool):
        return "Yes" if cell else "No"
    if isinstance(cell, Decimal | int | float):
        return number_text(cell, kind)
    text = clean(str(cell))
    if kind == CellKind.DATE:
        parsed = parse_date(text)
        return day_words(parsed) if parsed is not None else text
    return text


def naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(tzinfo=None)
