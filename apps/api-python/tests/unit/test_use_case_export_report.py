"""``ExportReport`` and the three screen exports: the routine's document is built into a file
by the writer whose content type the document names, off the event loop, with the name and
type the document carries; a document naming a type no writer owns is an integrity bug."""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from xcode_api.application.caller import Caller
from xcode_api.application.errors import IntegrityBug
from xcode_api.application.reports.export_report import ExportReport, ExportReportQuery
from xcode_api.application.reports.files import build_file
from xcode_api.application.revenue.export_week import ExportRevenueWeek, ExportRevenueWeekQuery
from xcode_api.domain.identity import Principal
from xcode_api.domain.reports import (
    PDF_CONTENT_TYPE,
    XLSX_CONTENT_TYPE,
    CellKind,
    ExportFormat,
    ReportColumn,
    ReportDocument,
    ReportFigure,
)

from ..support.clock import ManualClock
from ..support.fakes import (
    FakeReportsRepository,
    FakeRevenueRepository,
    FakeSetupRepository,
    FakeTenancyRepository,
)


class _Writer:
    def __init__(self, content_type: str, content: bytes) -> None:
        self.content_type = content_type
        self.content = content
        self.documents: list[ReportDocument] = []
        self.threads: list[str] = []

    def write(self, document: ReportDocument) -> bytes:
        self.documents.append(document)
        self.threads.append(threading.current_thread().name)
        return self.content


def _document(content_type: str) -> ReportDocument:
    return ReportDocument(
        group="fleet",
        report="net",
        title="Net by vehicle",
        from_date=date(2026, 10, 1),
        to_date=date(2026, 10, 9),
        business_date=date(2026, 10, 9),
        headline=ReportFigure("Net", Decimal(0), CellKind.NET),
        figures=(),
        columns=(ReportColumn("vehicle", "Vehicle", CellKind.VEHICLE, False),),
        rows=(),
        total=0,
        totals=(None,),
        organization="XCODE",
        period="1 Oct 2026 to 9 Oct 2026",
        filters="All companies",
        exported_by="Ann Owner",
        exported_on=datetime(2026, 10, 9, 7, tzinfo=UTC),
        currency="KES",
        file_name="Net by vehicle 1 Oct 2026 to 9 Oct 2026."
        + ("pdf" if content_type == PDF_CONTENT_TYPE else "xlsx"),
        content_type=content_type,
    )


def _world() -> tuple[FakeReportsRepository, Caller]:
    tenancy = FakeTenancyRepository()
    owner = tenancy.add_member()
    setup = FakeSetupRepository(tenancy)
    reports = FakeReportsRepository(setup, FakeRevenueRepository(setup))
    principal = Principal(owner, "phone-1", 0, tenancy.organization_id, "Owner", ())
    return reports, Caller(principal, "req-1")


async def test_the_writer_is_chosen_by_the_documents_content_type_and_runs_off_the_loop() -> None:
    xlsx, pdf = _Writer(XLSX_CONTENT_TYPE, b"PK..."), _Writer(PDF_CONTENT_TYPE, b"%PDF-1.4")
    writers = {ExportFormat.XLSX: xlsx, ExportFormat.PDF: pdf}
    file = await build_file(writers, _document(PDF_CONTENT_TYPE))
    assert (file.content, file.content_type) == (b"%PDF-1.4", PDF_CONTENT_TYPE)
    assert file.file_name == "Net by vehicle 1 Oct 2026 to 9 Oct 2026.pdf"
    assert xlsx.documents == []
    assert pdf.threads and pdf.threads[0] != threading.main_thread().name


async def test_a_document_without_a_writer_is_an_integrity_bug() -> None:
    writers = {ExportFormat.XLSX: _Writer(XLSX_CONTENT_TYPE, b"PK...")}
    with pytest.raises(IntegrityBug):
        await build_file(writers, _document(PDF_CONTENT_TYPE))


async def test_the_report_export_passes_the_query_and_names_the_file_from_the_document() -> None:
    reports, caller = _world()
    xlsx = _Writer(XLSX_CONTENT_TYPE, b"PK...")
    clock = ManualClock(datetime(2026, 10, 9, 7, tzinfo=UTC))
    use_case = ExportReport(reports, {ExportFormat.XLSX: xlsx}, clock)
    file = await use_case.execute(
        ExportReportQuery(
            caller, "fleet", "net", date(2026, 10, 1), date(2026, 10, 9), None, None, None, " XLSX "
        )
    )
    assert file.file_name == "Net by vehicle 1 Oct 2026 to 9 Oct 2026.xlsx"
    assert file.content_type == XLSX_CONTENT_TYPE
    assert file.content == b"PK..."
    assert xlsx.documents[0].title == "Net by vehicle"
    assert reports.setup.tenancy.log[-1].reason == (
        "Exported Net by vehicle for 1 Oct 2026 to 9 Oct 2026 to Excel"
    )


async def test_a_screen_export_uses_the_same_writers() -> None:
    reports, caller = _world()
    pdf = _Writer(PDF_CONTENT_TYPE, b"%PDF-1.4")
    use_case = ExportRevenueWeek(reports, {ExportFormat.PDF: pdf}, ManualClock())
    file = await use_case.execute(ExportRevenueWeekQuery(caller, None, None, "pdf"))
    assert file.content_type == PDF_CONTENT_TYPE
    assert file.file_name.startswith("Revenue ")
    assert file.file_name.endswith(".pdf")
    assert reports.setup.tenancy.log[-1].reason.endswith(" to PDF")
