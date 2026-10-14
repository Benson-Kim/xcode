"""The Excel adapter (XlsxWriter): a report document as one worksheet laid out as the expenses-and-
reports inventory describes the workbook. Every text goes through ``write_string`` into a
workbook that never turns a string into a formula, a number or a link; a text that begins like a
formula also gets the quote prefix, so Excel keeps it text when the cell is edited
(``docs/12-security.md`` 2.8); the bands, figure labels, headers and totals words, which carry
the display name and catalogue names, always have it. Numbers are numbers with their format,
dates are day serials; nothing is summed here: the footer is the document's ``totals``."""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

import xlsxwriter
from xlsxwriter.format import Format
from xlsxwriter.worksheet import Worksheet

from ...domain.reports import XLSX_CONTENT_TYPE, CellKind, ReportColumn, ReportDocument
from . import layout

_BAND = "#F3F6FA"
_INK = "#1F2A44"
_HEAD = "#E3E9F2"
_NUMBER_FORMATS = {
    CellKind.MONEY: "#,##0.00",
    CellKind.NET: "#,##0.00;[Red]-#,##0.00",
    CellKind.COUNT: "#,##0",
    CellKind.QUANTITY: "#,##0.###",
    CellKind.PERCENT: '0.0"%"',
}
_WIDTHS = {
    CellKind.TEXT: 28,
    CellKind.VEHICLE: 16,
    CellKind.DATE: 14,
    CellKind.MONEY: 16,
    CellKind.NET: 16,
    CellKind.COUNT: 10,
    CellKind.QUANTITY: 12,
    CellKind.PERCENT: 10,
}
_TITLE_ROW = 0
_SUBTITLE_ROW = 1
_STAMP_ROW = 2
_FIGURE_LABEL_ROW = 4
_FIGURE_VALUE_ROW = 5
_HEADER_ROW = 7
_FIRST_DATA_ROW = 8


class XlsxWriterAdapter:
    """``ReportFileWriter`` for ``.xlsx`` files."""

    content_type = XLSX_CONTENT_TYPE

    def write(self, document: ReportDocument) -> bytes:
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(
            buffer,
            {
                "in_memory": True,
                "strings_to_formulas": False,
                "strings_to_numbers": False,
                "strings_to_urls": False,
            },
        )
        workbook.set_properties(
            {
                "title": layout.clean(document.title),
                "author": layout.clean(document.organization),
                "company": layout.clean(document.organization),
                "created": layout.naive_utc(document.exported_on),
            }
        )
        sheet = workbook.add_worksheet(layout.sheet_name(document.title))
        formats = _Formats(workbook)
        columns = document.columns
        last_col = max(len(columns) - 1, 0)
        _write_bands(sheet, document, formats, last_col)
        _write_figures(sheet, document, formats)
        _write_header(sheet, columns, formats)
        last_row = _write_rows(sheet, document, formats)
        last_row = _write_totals(sheet, document, formats, last_row)
        for index, column in enumerate(columns):
            sheet.set_column(index, index, _WIDTHS.get(column.kind, 16))
        sheet.freeze_panes(_FIRST_DATA_ROW, 0)
        sheet.repeat_rows(_HEADER_ROW)
        sheet.autofilter(_HEADER_ROW, 0, max(last_row, _HEADER_ROW), last_col)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.set_footer(f"&L{layout.clean(layout.footer_words(document))}&RPage &P of &N")
        workbook.close()
        return buffer.getvalue()


class _Formats:
    def __init__(self, workbook: xlsxwriter.Workbook) -> None:
        add = workbook.add_format
        label = {"quote_prefix": True}
        self.title = add(
            {**label, "bold": True, "font_size": 16, "font_color": "#FFFFFF", "bg_color": _INK}
        )
        self.subtitle = add({**label, "font_color": "#4A5568"})
        self.stamp = add({**label, "font_color": "#4A5568", "italic": True})
        self.figure_label = add({**label, "bold": True, "font_size": 9, "font_color": "#4A5568"})
        self.header = add({**label, "bold": True, "bottom": 1, "bg_color": _HEAD})
        self.totals_text = add({**label, "bold": True, "top": 1})
        self.text = {(False, False): add({})}
        self.text[(True, False)] = add({"bg_color": _BAND})
        self.text[(False, True)] = add({"quote_prefix": True})
        self.text[(True, True)] = add({"bg_color": _BAND, "quote_prefix": True})
        self.date = {
            False: add({"num_format": "d mmm yyyy"}),
            True: add({"num_format": "d mmm yyyy", "bg_color": _BAND}),
        }
        self.number: dict[tuple[CellKind, bool], Format] = {}
        self.figure_value: dict[CellKind, Format] = {}
        self.totals_number: dict[CellKind, Format] = {}
        for kind, number_format in _NUMBER_FORMATS.items():
            self.number[(kind, False)] = add({"num_format": number_format})
            self.number[(kind, True)] = add({"num_format": number_format, "bg_color": _BAND})
            self.figure_value[kind] = add(
                {"num_format": number_format, "bold": True, "font_size": 12}
            )
            self.totals_number[kind] = add({"num_format": number_format, "bold": True, "top": 1})
        self.plain_number = add({"num_format": "#,##0.00"})

    def number_for(self, kind: CellKind, banded: bool) -> Format:
        return self.number.get((kind, banded), self.number[(CellKind.MONEY, banded)])

    def figure_for(self, kind: CellKind) -> Format:
        return self.figure_value.get(kind, self.figure_value[CellKind.MONEY])

    def total_for(self, kind: CellKind) -> Format:
        return self.totals_number.get(kind, self.totals_number[CellKind.MONEY])


def _write_bands(
    sheet: Worksheet, document: ReportDocument, formats: _Formats, last_col: int
) -> None:
    title = layout.clean(document.title)
    if last_col > 0:
        sheet.merge_range(_TITLE_ROW, 0, _TITLE_ROW, last_col, title, formats.title)
        sheet.merge_range(
            _SUBTITLE_ROW,
            0,
            _SUBTITLE_ROW,
            last_col,
            layout.clean(layout.subtitle(document)),
            formats.subtitle,
        )
        sheet.merge_range(
            _STAMP_ROW, 0, _STAMP_ROW, last_col, layout.clean(layout.stamp(document)), formats.stamp
        )
    else:
        sheet.write_string(_TITLE_ROW, 0, title, formats.title)
        sheet.write_string(
            _SUBTITLE_ROW, 0, layout.clean(layout.subtitle(document)), formats.subtitle
        )
        sheet.write_string(_STAMP_ROW, 0, layout.clean(layout.stamp(document)), formats.stamp)
    sheet.set_row(_TITLE_ROW, 26)


def _write_figures(sheet: Worksheet, document: ReportDocument, formats: _Formats) -> None:
    for index, figure in enumerate((document.headline, *document.figures)):
        label = layout.clean(layout.figure_label(figure, document.currency))
        sheet.write_string(_FIGURE_LABEL_ROW, index, label, formats.figure_label)
        sheet.write_number(
            _FIGURE_VALUE_ROW, index, float(figure.value), formats.figure_for(figure.kind)
        )


def _write_header(sheet: Worksheet, columns: tuple[ReportColumn, ...], formats: _Formats) -> None:
    for index, column in enumerate(columns):
        sheet.write_string(_HEADER_ROW, index, layout.clean(column.label), formats.header)


def _write_rows(sheet: Worksheet, document: ReportDocument, formats: _Formats) -> int:
    row_number = _FIRST_DATA_ROW - 1
    for offset, row in enumerate(document.rows):
        row_number = _FIRST_DATA_ROW + offset
        banded = offset % 2 == 1
        for index, column in enumerate(document.columns):
            cell = row[index] if index < len(row) else None
            _write_cell(
                sheet, row_number, index, cell, kind=column.kind, banded=banded, formats=formats
            )
    return row_number


def _write_cell(
    sheet: Worksheet,
    row: int,
    col: int,
    cell: Any,
    *,
    kind: CellKind,
    banded: bool,
    formats: _Formats,
) -> None:
    if cell is None:
        sheet.write_blank(row, col, None, formats.text[(banded, False)])
        return
    if isinstance(cell, bool):
        sheet.write_string(row, col, "Yes" if cell else "No", formats.text[(banded, False)])
        return
    if isinstance(cell, Decimal | int | float):
        sheet.write_number(row, col, float(cell), formats.number_for(kind, banded))
        return
    text = layout.clean(str(cell))
    if kind == CellKind.DATE:
        day = layout.parse_date(text)
        if day is not None:
            sheet.write_datetime(row, col, day, formats.date[banded])
            return
    sheet.write_string(row, col, text, formats.text[(banded, layout.looks_like_formula(text))])


def _write_totals(
    sheet: Worksheet, document: ReportDocument, formats: _Formats, last_row: int
) -> int:
    if not any(column.sum for column in document.columns):
        return last_row
    row = max(last_row + 1, _FIRST_DATA_ROW)
    sheet.write_string(row, 0, layout.rows_words(document.total), formats.totals_text)
    for index, column in enumerate(document.columns):
        total = document.totals[index] if index < len(document.totals) else None
        if index == 0:
            continue
        if column.sum and total is not None:
            sheet.write_number(row, index, float(total), formats.total_for(column.kind))
        else:
            sheet.write_blank(row, index, None, formats.totals_text)
    return row
