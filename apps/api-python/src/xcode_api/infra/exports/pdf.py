"""The PDF adapter (ReportLab's canvas): a report document on A4 landscape pages laid out as the
expenses-and-reports inventory describes the PDF, with Figtree Regular, Figtree Bold and
Fraunces Bold embedded from the package's own copies of the fonts (never the system's). The rows
are paginated first and drawn second, so every footer knows the page count. Nothing is summed
here."""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from ...domain.reports import PDF_CONTENT_TYPE, CellKind, ReportColumn, ReportDocument
from . import layout

FONTS_DIR = Path(__file__).resolve().parent / "fonts"
REGULAR = "Figtree"
BOLD = "Figtree-Bold"
DISPLAY = "Fraunces-Bold"
_FONT_FILES = {
    REGULAR: "Figtree-Regular.ttf",
    BOLD: "Figtree-Bold.ttf",
    DISPLAY: "Fraunces-Bold.ttf",
}
_registered = False
_register_lock = threading.Lock()

_SIZE = landscape(A4)
PAGE_WIDTH: float = float(_SIZE[0])
PAGE_HEIGHT: float = float(_SIZE[1])
_MARGIN = 36.0
_BAND_HEIGHT = 46.0
_ROW_HEIGHT = 15.0
_HEADER_HEIGHT = 18.0
_INK = (0.12, 0.16, 0.27)
_ACCENT = (0.16, 0.46, 0.80)
_BAND = (0.95, 0.96, 0.98)
_HEAD = (0.89, 0.91, 0.95)
_TOTALS = (0.93, 0.95, 0.99)
_RED = (0.72, 0.11, 0.11)
_GREY = (0.35, 0.40, 0.48)
_NUMERIC = (CellKind.MONEY, CellKind.NET, CellKind.COUNT, CellKind.QUANTITY, CellKind.PERCENT)
_WEIGHTS = {
    CellKind.TEXT: 3.0,
    CellKind.VEHICLE: 1.6,
    CellKind.DATE: 1.5,
    CellKind.MONEY: 1.7,
    CellKind.NET: 1.7,
    CellKind.COUNT: 1.0,
    CellKind.QUANTITY: 1.2,
    CellKind.PERCENT: 1.4,
}


def register_fonts() -> None:
    """Register the three brand fonts once per process."""
    global _registered  # noqa: PLW0603 - a process-wide registration guard
    with _register_lock:
        if _registered:
            return
        for name, file_name in _FONT_FILES.items():
            pdfmetrics.registerFont(TTFont(name, str(FONTS_DIR / file_name)))
        _registered = True


@dataclass(frozen=True, slots=True)
class _Page:
    first_row: int
    last_row: int
    totals: bool


class ReportLabAdapter:
    """``ReportFileWriter`` for ``.pdf`` files."""

    content_type = PDF_CONTENT_TYPE

    def write(self, document: ReportDocument) -> bytes:
        register_fonts()
        buffer = io.BytesIO()
        pdf = canvas.Canvas(
            buffer,
            pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
            pageCompression=1,
            initialFontName=REGULAR,
        )
        pdf.setTitle(document.title)
        pdf.setAuthor(document.organization)
        pdf.setCreator(layout.BRAND)
        pdf.setSubject(layout.period_words(document))
        widths = _column_widths(document.columns)
        pages = _paginate(document)
        for number, page in enumerate(pages, start=1):
            _draw_page(pdf, document, widths, page, number=number, pages=len(pages))
            pdf.showPage()
        pdf.save()
        return buffer.getvalue()


def _column_widths(columns: tuple[ReportColumn, ...]) -> list[float]:
    available = PAGE_WIDTH - 2 * _MARGIN
    if not columns:
        return []
    weights = [_WEIGHTS.get(column.kind, 1.5) for column in columns]
    total = sum(weights)
    return [available * weight / total for weight in weights]


def _first_page_table_top() -> float:
    return PAGE_HEIGHT - _MARGIN - _BAND_HEIGHT - 22 - 70


def _later_page_table_top() -> float:
    return PAGE_HEIGHT - _MARGIN - _BAND_HEIGHT - 22


def _rows_fitting(table_top: float, totals_row: bool) -> int:
    bottom = _MARGIN + 24
    space = table_top - _HEADER_HEIGHT - bottom - (_ROW_HEIGHT if totals_row else 0)
    return max(int(space // _ROW_HEIGHT), 1)


def _paginate(document: ReportDocument) -> list[_Page]:
    count = len(document.rows)
    has_totals = any(column.sum for column in document.columns) and count > 0
    pages: list[_Page] = []
    first = 0
    while True:
        top = _first_page_table_top() if not pages else _later_page_table_top()
        fitting = _rows_fitting(top, False)
        last = min(first + fitting, count)
        remaining = count - last
        totals_here = has_totals and remaining == 0 and last - first <= _rows_fitting(top, True)
        if has_totals and remaining == 0 and not totals_here:
            last -= 1
            remaining = 1
            totals_here = False
        pages.append(_Page(first, last, totals_here))
        if remaining == 0 and (totals_here or not has_totals):
            return pages
        first = last


def _draw_page(
    pdf: canvas.Canvas,
    document: ReportDocument,
    widths: list[float],
    page: _Page,
    *,
    number: int,
    pages: int,
) -> None:
    _draw_band(pdf, document)
    top = _later_page_table_top()
    if number == 1:
        _draw_figures(pdf, document)
        top = _first_page_table_top()
    if not document.rows:
        pdf.setFont(REGULAR, 11)
        pdf.setFillColorRGB(*_GREY)
        pdf.drawCentredString(PAGE_WIDTH / 2, top - 40, layout.EMPTY_WORDS)
    else:
        _draw_table(pdf, document, widths, page, top)
    _draw_footer(pdf, document, number, pages)


def _draw_band(pdf: canvas.Canvas, document: ReportDocument) -> None:
    top = PAGE_HEIGHT - _MARGIN
    pdf.setFillColorRGB(*_INK)
    pdf.rect(_MARGIN, top - _BAND_HEIGHT, PAGE_WIDTH - 2 * _MARGIN, _BAND_HEIGHT, stroke=0, fill=1)
    pdf.setFillColorRGB(*_ACCENT)
    pdf.rect(_MARGIN, top - _BAND_HEIGHT, 6, _BAND_HEIGHT, stroke=0, fill=1)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont(DISPLAY, 18)
    pdf.drawString(_MARGIN + 16, top - 30, _fit(pdf, document.title, DISPLAY, 18, 420))
    pdf.setFont(REGULAR, 10)
    pdf.drawRightString(PAGE_WIDTH - _MARGIN - 12, top - 28, layout.period_words(document))
    pdf.setFillColorRGB(*_GREY)
    pdf.setFont(REGULAR, 9)
    line = top - _BAND_HEIGHT - 14
    pdf.drawString(_MARGIN, line, _fit(pdf, layout.subtitle(document), REGULAR, 9, 500))
    pdf.drawRightString(PAGE_WIDTH - _MARGIN, line, layout.stamp(document))


def _draw_figures(pdf: canvas.Canvas, document: ReportDocument) -> None:
    top = PAGE_HEIGHT - _MARGIN - _BAND_HEIGHT - 30
    card_height = 56.0
    headline_width = 220.0
    pdf.setFillColorRGB(*_TOTALS)
    pdf.roundRect(_MARGIN, top - card_height, headline_width, card_height, 6, stroke=0, fill=1)
    pdf.setFillColorRGB(*_GREY)
    pdf.setFont(BOLD, 8)
    pdf.drawString(
        _MARGIN + 12, top - 16, layout.figure_label(document.headline, document.currency)
    )
    pdf.setFillColorRGB(*(_RED if _negative(document.headline.value) else _INK))
    pdf.setFont(DISPLAY, 20)
    pdf.drawString(
        _MARGIN + 12, top - 42, layout.number_text(document.headline.value, document.headline.kind)
    )
    x = _MARGIN + headline_width + 14
    tile_width = 150.0
    for figure in document.figures:
        if x + tile_width > PAGE_WIDTH - _MARGIN:
            break
        pdf.setFillColorRGB(*_BAND)
        pdf.roundRect(x, top - card_height, tile_width, card_height, 6, stroke=0, fill=1)
        pdf.setFillColorRGB(*_GREY)
        pdf.setFont(BOLD, 7.5)
        pdf.drawString(
            x + 10,
            top - 16,
            _fit(pdf, layout.figure_label(figure, document.currency), BOLD, 7.5, tile_width - 20),
        )
        pdf.setFillColorRGB(
            *(_RED if _negative(figure.value) and figure.kind == CellKind.NET else _INK)
        )
        pdf.setFont(BOLD, 14)
        pdf.drawString(x + 10, top - 40, layout.number_text(figure.value, figure.kind))
        x += tile_width + 10


def _draw_table(
    pdf: canvas.Canvas, document: ReportDocument, widths: list[float], page: _Page, top: float
) -> None:
    columns = document.columns
    y = top - _HEADER_HEIGHT
    pdf.setFillColorRGB(*_HEAD)
    pdf.rect(_MARGIN, y, PAGE_WIDTH - 2 * _MARGIN, _HEADER_HEIGHT, stroke=0, fill=1)
    pdf.setFillColorRGB(*_INK)
    pdf.setFont(BOLD, 8.5)
    x = _MARGIN
    for column, width in zip(columns, widths, strict=False):
        _draw_text(
            pdf,
            column.label,
            x,
            y + 5,
            width=width,
            right=column.kind in _NUMERIC,
            font=BOLD,
            size=8.5,
        )
        x += width
    for index in range(page.first_row, page.last_row):
        y -= _ROW_HEIGHT
        if index % 2 == 1:
            pdf.setFillColorRGB(*_BAND)
            pdf.rect(_MARGIN, y, PAGE_WIDTH - 2 * _MARGIN, _ROW_HEIGHT, stroke=0, fill=1)
        row = document.rows[index]
        x = _MARGIN
        for position, (column, width) in enumerate(zip(columns, widths, strict=False)):
            cell = row[position] if position < len(row) else None
            _draw_cell(pdf, cell, column, x=x, y=y, width=width)
            x += width
    if page.totals:
        y -= _ROW_HEIGHT
        pdf.setFillColorRGB(*_TOTALS)
        pdf.rect(_MARGIN, y, PAGE_WIDTH - 2 * _MARGIN, _ROW_HEIGHT, stroke=0, fill=1)
        pdf.setFillColorRGB(*_INK)
        x = _MARGIN
        for position, (column, width) in enumerate(zip(columns, widths, strict=False)):
            if position == 0:
                words = layout.rows_words(document.total)
            else:
                total = document.totals[position] if position < len(document.totals) else None
                words = (
                    layout.number_text(total, column.kind)
                    if column.sum and total is not None
                    else ""
                )
            _draw_text(pdf, words, x, y + 4, width=width, right=position != 0, font=BOLD, size=8.5)
            x += width


def _draw_cell(
    pdf: canvas.Canvas, cell: Any, column: ReportColumn, *, x: float, y: float, width: float
) -> None:
    words = layout.cell_words(cell, column.kind)
    numeric = column.kind in _NUMERIC and isinstance(cell, Decimal | int | float)
    if column.kind == CellKind.NET and numeric and _negative(cell):
        pdf.setFillColorRGB(*_RED)
    else:
        pdf.setFillColorRGB(*_INK)
    if column.kind == CellKind.PERCENT and numeric:
        share = max(min(float(cell) / 100.0, 1.0), 0.0)
        bar_width = max(width - 46, 10)
        pdf.setFillColorRGB(*_HEAD)
        pdf.rect(x + 4, y + 5, bar_width, 5, stroke=0, fill=1)
        pdf.setFillColorRGB(*_ACCENT)
        pdf.rect(x + 4, y + 5, bar_width * share, 5, stroke=0, fill=1)
        pdf.setFillColorRGB(*_INK)
        _draw_text(pdf, words, x, y + 4, width=width, right=True, font=REGULAR, size=8.5)
        return
    _draw_text(pdf, words, x, y + 4, width=width, right=numeric, font=REGULAR, size=8.5)


def _draw_text(
    pdf: canvas.Canvas,
    words: str,
    x: float,
    y: float,
    *,
    width: float,
    right: bool,
    font: str,
    size: float,
) -> None:
    pdf.setFont(font, size)
    text = _fit(pdf, words, font, size, width - 8)
    if right:
        pdf.drawRightString(x + width - 4, y, text)
    else:
        pdf.drawString(x + 4, y, text)


def _fit(pdf: canvas.Canvas, words: str, font: str, size: float, width: float) -> str:
    if pdf.stringWidth(words, font, size) <= width:
        return words
    ellipsis = "…"
    kept = words
    while kept and pdf.stringWidth(kept + ellipsis, font, size) > width:
        kept = kept[:-1]
    return kept + ellipsis


def _draw_footer(pdf: canvas.Canvas, document: ReportDocument, number: int, pages: int) -> None:
    pdf.setFillColorRGB(*_GREY)
    pdf.setFont(REGULAR, 8)
    pdf.drawString(_MARGIN, _MARGIN - 10, _fit(pdf, layout.footer_words(document), REGULAR, 8, 600))
    pdf.drawRightString(PAGE_WIDTH - _MARGIN, _MARGIN - 10, f"Page {number} of {pages}")


def _negative(value: Any) -> bool:
    return isinstance(value, Decimal | int | float) and value < 0
