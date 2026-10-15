"""The two export adapters on fixed documents, read back as .NET's tests read theirs: the Excel
file as the zip of XML parts it is (a text starting like a formula stays a string with the
quote prefix and no formula element, numbers are numbers with their formats, dates are serials,
the header is frozen and repeated, the totals row, the footer, a 31-character sheet name), the
PDF with ``pypdf`` (A4 landscape, the three fonts embedded, the title and the page numbers in
the text). Two builds of one document are byte for byte the same."""

from __future__ import annotations

import io
import re
from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal
from typing import Any

import reportlab.rl_config
from pypdf import PdfReader

from xcode_api.domain.reports import (
    PDF_CONTENT_TYPE,
    XLSX_CONTENT_TYPE,
    CellKind,
    ReportColumn,
    ReportDocument,
    ReportFigure,
)
from xcode_api.infra.exports.pdf import ReportLabAdapter
from xcode_api.infra.exports.xlsx import XlsxWriterAdapter

from ..support.export_files import NS, Workbook, embedded_fonts

reportlab.rl_config.invariant = 1

COLUMNS = (
    ReportColumn("date", "Date", CellKind.DATE, False),
    ReportColumn("vehicle", "Vehicle", CellKind.VEHICLE, False),
    ReportColumn("note", "Note", CellKind.TEXT, False),
    ReportColumn("count", "Entries", CellKind.COUNT, True),
    ReportColumn("quantity", "Quantity", CellKind.QUANTITY, True),
    ReportColumn("amount", "Amount", CellKind.MONEY, True),
    ReportColumn("net", "Net", CellKind.NET, True),
    ReportColumn("share", "Share", CellKind.PERCENT, False),
)
ROWS = (
    (
        "2026-10-05",
        "KDA 482M",
        "=SUM(A1:A9)",
        3,
        Decimal("2.500"),
        Decimal("4000.00"),
        Decimal("-1250.50"),
        Decimal("57.5"),
    ),
    (
        "2026-10-06",
        "KDB 111A",
        "+plain",
        1,
        Decimal(1),
        Decimal("250.00"),
        Decimal("250.00"),
        Decimal("42.5"),
    ),
    ("2026-10-07", "KDC 200B", None, 0, Decimal(0), Decimal(0), Decimal(0), Decimal(0)),
)
TOTALS = (
    None,
    None,
    None,
    Decimal(4),
    Decimal("3.5"),
    Decimal("4250.00"),
    Decimal("-1000.50"),
    None,
)


def document(
    *,
    title: str = "Net by vehicle",
    rows: tuple[tuple[Any, ...], ...] = ROWS,
    content_type: str = XLSX_CONTENT_TYPE,
    period: str | None = "1 Oct 2026 to 9 Oct 2026",
) -> ReportDocument:
    return ReportDocument(
        group="fleet",
        report="net",
        title=title,
        from_date=date_type(2026, 10, 1) if period else None,
        to_date=date_type(2026, 10, 9) if period else None,
        business_date=date_type(2026, 10, 9),
        headline=ReportFigure("Net", Decimal("-1000.50"), CellKind.NET),
        figures=(
            ReportFigure("Revenue", Decimal("4250"), CellKind.MONEY),
            ReportFigure("Reached", Decimal("57.5"), CellKind.PERCENT),
            ReportFigure("Missing days", Decimal(4), CellKind.COUNT),
        ),
        columns=COLUMNS,
        rows=rows,
        total=len(rows),
        totals=TOTALS,
        organization="Metro Trans",
        period=period,
        filters="All companies",
        exported_by="Ann Owner",
        exported_on=datetime(2026, 10, 9, 7, 30, tzinfo=UTC),
        currency="KES",
        file_name=f"{title}.{'pdf' if content_type == PDF_CONTENT_TYPE else 'xlsx'}",
        content_type=content_type,
    )


def many_rows(count: int) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            f"2026-{1 + index // 28:02d}-{1 + index % 28:02d}",
            f"KD{index:03d}",
            "note",
            index,
            Decimal(1),
            Decimal(100),
            Decimal(50),
            Decimal(10),
        )
        for index in range(count)
    )


def test_a_cell_starting_with_equals_stays_text() -> None:
    book = Workbook(XlsxWriterAdapter().write(document()))
    assert book.sheet.find(".//m:f", NS) is None
    for reference, expected in (("C9", "=SUM(A1:A9)"), ("C10", "+plain")):
        assert book.text(reference) == expected
        assert book.xf(reference).get("quotePrefix") == "1"
    assert book.text("B9") == "KDA 482M"
    assert book.xf("B9").get("quotePrefix") is None


def test_numbers_are_numbers_with_their_formats_and_dates_are_serials() -> None:
    book = Workbook(XlsxWriterAdapter().write(document()))
    expectations = {
        "D9": ("3", "#,##0"),
        "E9": ("2.5", "#,##0.###"),
        "F9": ("4000", "#,##0.00"),
        "G9": ("-1250.5", "#,##0.00;[Red]-#,##0.00"),
        "H9": ("57.5", '0.0"%"'),
        "A9": ("46300", "d mmm yyyy"),
    }
    for reference, (value, number_format) in expectations.items():
        assert book.number(reference) == value, reference
        assert book.number_format(reference) == number_format, reference


def test_the_bands_figures_header_totals_and_footer_are_laid_out_as_the_rules_say() -> None:
    book = Workbook(XlsxWriterAdapter().write(document()))
    assert book.text("A1") == "Net by vehicle"
    assert book.text("A2") == "Metro Trans  ·  1 Oct 2026 to 9 Oct 2026  ·  All companies"
    assert book.text("A3") == "Exported 9 Oct 2026 by Ann Owner"
    assert [book.text(f"{column}5") for column in "ABCD"] == [
        "NET (KES)",
        "REVENUE (KES)",
        "REACHED",
        "MISSING DAYS",
    ]
    assert book.number("A6") == "-1000.5"
    assert [book.text(f"{column}8") for column in "ABCDEFGH"] == [
        "Date",
        "Vehicle",
        "Note",
        "Entries",
        "Quantity",
        "Amount",
        "Net",
        "Share",
    ]
    assert book.text("A12") == "3 rows"
    assert book.number("F12") == "4250"
    assert book.number("G12") == "-1000.5"
    assert not book.has("A13")
    pane = book.sheet.find(".//m:pane", NS)
    assert pane is not None
    assert (pane.get("ySplit"), pane.get("topLeftCell"), pane.get("state")) == ("8", "A9", "frozen")
    footer = book.sheet.find(".//m:oddFooter", NS)
    assert footer is not None and footer.text is not None
    assert "XCODE Fleet finance | Net by vehicle, 1 Oct 2026 to 9 Oct 2026" in footer.text
    assert "Page &P of &N" in footer.text
    auto_filter = book.sheet.find("m:autoFilter", NS)
    assert auto_filter is not None and auto_filter.get("ref") == "A8:H12"
    setup = book.sheet.find("m:pageSetup", NS)
    assert setup is not None and setup.get("orientation") == "landscape"
    assert book.sheet_name == "Net by vehicle"
    assert "2026-10-09T07:30:00Z" in book.core


def test_a_long_title_gives_a_sheet_name_of_at_most_31_characters_without_forbidden_marks() -> None:
    title = "Petty cash: waiting/approved? [all] *of* the year 2026"
    book = Workbook(XlsxWriterAdapter().write(document(title=title)))
    assert book.sheet_name == "Petty cash waitingapproved all"
    assert len(book.sheet_name) <= 31
    assert not re.search(r"[:\\/?*\[\]]", book.sheet_name)


def test_an_undated_report_reads_as_at_and_an_empty_one_has_only_its_count_row() -> None:
    book = Workbook(XlsxWriterAdapter().write(document(rows=(), period=None)))
    assert book.text("A2") == "Metro Trans  ·  As at 9 Oct 2026  ·  All companies"
    assert book.text("A9") == "0 rows"
    assert not book.has("A10")


def test_two_builds_of_one_document_are_the_same_bytes() -> None:
    assert XlsxWriterAdapter().write(document()) == XlsxWriterAdapter().write(document())
    pdf = document(content_type=PDF_CONTENT_TYPE)
    assert ReportLabAdapter().write(pdf) == ReportLabAdapter().write(pdf)


def test_the_pdf_is_a4_landscape_with_the_three_fonts_embedded_and_numbered_pages() -> None:
    content = ReportLabAdapter().write(document(rows=many_rows(60), content_type=PDF_CONTENT_TYPE))
    reader = PdfReader(io.BytesIO(content))
    assert len(reader.pages) == 3
    box = reader.pages[0].mediabox
    assert (round(float(box.width)), round(float(box.height))) == (842, 595)
    assert embedded_fonts(reader) == {
        "Figtree-Regular": True,
        "Figtree-Bold": True,
        "Fraunces72pt-Bold": True,
    }
    first = reader.pages[0].extract_text()
    last = reader.pages[2].extract_text()
    assert "Net by vehicle" in first
    assert "Page 1 of 3" in first
    assert "Page 3 of 3" in last
    assert "60 rows" in last
    assert reader.metadata is not None
    assert reader.metadata.title == "Net by vehicle"
    assert reader.metadata.author == "Metro Trans"
    assert reader.metadata.creator == "XCODE Fleet finance"


def test_an_empty_pdf_says_there_is_nothing_to_show() -> None:
    content = ReportLabAdapter().write(document(rows=(), content_type=PDF_CONTENT_TYPE))
    reader = PdfReader(io.BytesIO(content))
    assert len(reader.pages) == 1
    assert "Nothing to show for these dates." in reader.pages[0].extract_text()
