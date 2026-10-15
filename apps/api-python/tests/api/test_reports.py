"""The report and export routes against the real database (``docs/06-http-contract.md``
2.13.2 to 2.13.5): the catalogue and a report page in wire order, each refusal's status and
sentence, a report as an Excel or PDF file (opened and read cell by cell, the name in
``Content-Disposition``, the change-log reason), the row bound, a scoped viewer's file, the
three screen exports listing what their screens list, 401, the route catalogue and the
statement budget of 2.

The business date is 7 Oct 2026, a Wednesday (the test clock in Nairobi). Antony Maina owns
the organization, Peter Otieno (Office admin) reviews petty cash and records central
expenses, Wanjiru Kamau (Fleet manager, North Star only) keeps a float, Grace Njeri (Revenue
clerk) may open no report. History before the first request is seeded as ``xcode_owner``."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from psycopg.types.json import Jsonb
from pypdf import PdfReader

from xcode_api.http.messages import MESSAGES
from xcode_api.http.routers.reports import router
from xcode_api.infra.exports.xlsx import XlsxWriterAdapter

from ..support.client import ApiFactory, AuthApi
from ..support.export_files import Workbook, embedded_fonts
from ..support.scenario import call
from ..support.setup_client import (
    FORBIDDEN,
    INVALID,
    NOT_FOUND,
    Member,
    join,
    ok,
    problem,
    statements,
)
from ..support.setup_rows import (
    Version,
    add_category,
    add_item,
    add_main_category,
    add_record,
    add_schedule,
    add_target,
)
from ..support.tenancy import Member as Person
from ..support.tenancy import add_company, add_vehicle, set_override, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

TODAY = "2026-10-07"
PERIOD = "from=2026-10-01&to=2026-10-07"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"
ACCESS_KEYS = ["businessDate", "firstDayOfWeek", "fleet", "pettyCash", "holders", "canExport"]
HOLDER_KEYS = ["id", "name", "active"]
TABLE_KEYS = [
    "group",
    "report",
    "title",
    "from",
    "to",
    "businessDate",
    "headline",
    "figures",
    "columns",
    "rows",
    "pageNumber",
    "pageSize",
    "total",
    "totals",
]
FIGURE_KEYS = ["label", "value", "kind"]
COLUMN_KEYS = ["key", "label", "kind", "sum"]
FLEET_REPORTS = ["net", "target", "moneyOut", "gaps", "savings"]
PETTY_REPORTS = ["cashBook", "managers", "vehicles", "items", "waiting", "sentBack", "rejected"]
REVIEWER_RIGHTS = (
    "pettycash.view",
    "pettycash.view_all",
    "pettycash.reports",
    "pettycash.export",
    "pettycash.approve_item",
)
HEADER_ROW = 8
FIRST_DATA_ROW = 9
SERIAL_EPOCH = date(1899, 12, 30)


@dataclass(frozen=True)
class World:
    api: AuthApi
    org: UUID
    owner: Member
    admin: Member
    clerk: Member
    teller: Member
    north: UUID
    south: UUID
    kda: UUID
    kdb: UUID
    kdc: UUID
    tyres: UUID


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


async def _person(api: AuthApi, org: UUID | None, role: str, phone: str, name: str) -> Member:
    joined = await join(api, email=f"{phone}@example.com", phone=phone, role=role)
    first, last = name.split()
    api.owner.execute(
        "UPDATE tenancy.memberships SET first_name = %s, last_name = %s WHERE user_id = %s",
        (first, last, joined.user_id),
    )
    if org is not None:
        set_scope(api.owner, joined.user_id, org, all_companies=True)
    return joined


def _routine(api: AuthApi, name: str, who: Member, org: UUID, *args: Any) -> Any:
    return call(api.owner, name, who.user_id, org, "req-seed", *args, api.clock.now())


@pytest.fixture
async def world(api: AuthApi) -> World:
    owner = await _person(api, None, "Owner", "0711000311", "Antony Maina")
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    org = UUID(str(row["id"]))
    set_scope(api.owner, owner.user_id, org, all_companies=True)
    admin = await _person(api, org, "Office admin", "0722000311", "Peter Otieno")
    clerk = await _person(api, None, "Fleet manager", "0733000311", "Wanjiru Kamau")
    teller = await _person(api, org, "Revenue clerk", "0744000311", "Grace Njeri")
    north = add_company(api.owner, org, "North Star")
    south = add_company(api.owner, org, "South Line")
    set_scope(api.owner, clerk.user_id, org, companies=[north])
    for right in REVIEWER_RIGHTS:
        set_override(api.owner, Person(admin.user_id, org, "", "", "", "", ""), right)
    api.owner.execute(
        "UPDATE tenancy.memberships SET approval_limit = 5000 WHERE user_id = %s",
        (admin.user_id,),
    )
    api.owner.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = 'days', back_limit_count = 30 "
        "WHERE organization_id = %s",
        (org,),
    )
    kda = add_vehicle(api.owner, org, north, "KDA 482M", joined_on=date(2026, 10, 1))
    kdb = add_vehicle(api.owner, org, north, "KDB 111A", joined_on=date(2026, 10, 5))
    kdc = add_vehicle(api.owner, org, south, "KDC 200B", joined_on=date(2026, 9, 1))
    add_target(api.owner, org, kda, 1, date(2026, 10, 1), 7000)
    add_target(api.owner, org, kdc, 1, date(2026, 9, 1), 7000)
    for day, amount in ((1, 4500), (2, 5200), (5, 3000)):
        add_record(api.owner, org, kda, date(2026, 10, day), amount, recorder=owner.user_id)
    for day in range(1, 6):
        add_record(api.owner, org, kdc, date(2026, 10, day), 2000, recorder=owner.user_id)
    running = add_main_category(api.owner, org, "Running")
    repairs = add_category(api.owner, org, "Repairs", bucket=1, main_category=running)
    tyres = add_item(api.owner, org, repairs, "Tyres")
    diesel = add_item(
        api.owner, org, add_category(api.owner, org, "Fuelling", bucket=None), "Diesel"
    )
    add_schedule(
        api.owner,
        org,
        Version(
            date(2026, 10, 1), {kda: 300}, name="Parking", kind=1, frequency=3, day=5, bucket=2
        ),
    )
    add_schedule(
        api.owner,
        org,
        Version(date(2026, 10, 1), {kdc: 100}, name="Tyre fund", kind=2, frequency=1, day=None),
    )
    _routine(
        api,
        "pettycash_entry_create",
        owner,
        org,
        None,
        "cash",
        date(2026, 10, 1),
        Decimal(10000),
        clerk.user_id,
        None,
        None,
        None,
        None,
        None,
        False,
        None,
    )
    saved = _routine(
        api,
        "pettycash_entry_create",
        clerk,
        org,
        None,
        "expense",
        date(2026, 10, 2),
        Decimal(1500),
        None,
        kda,
        tyres,
        Decimal(2),
        None,
        None,
        False,
        None,
    )
    _routine(api, "pettycash_entry_approve", admin, org, UUID(saved["id"]), saved["version"])
    _routine(
        api,
        "pettycash_entry_create",
        clerk,
        org,
        None,
        "expense",
        date(2026, 10, 3),
        Decimal(3000),
        None,
        kda,
        diesel,
        Decimal(1),
        None,
        "=2+2",
        False,
        None,
    )
    _routine(
        api,
        "expenses_entry_create",
        admin,
        org,
        None,
        date(2026, 10, 6),
        tyres,
        Decimal(4),
        Decimal(1200),
        None,
        Jsonb([{"vehicle_id": str(kdc), "amount": "4800"}]),
    )
    return World(api, org, owner, admin, clerk, teller, north, south, kda, kdb, kdc, tyres)


def get(world: World, who: Member | None, path: str) -> Any:
    headers = None if who is None else who.headers
    return world.api.client.get(f"/setup{path}", headers=headers)


def sentence(code: str, **parameters: str) -> str:
    text = MESSAGES[code].sentence(parameters)
    assert text is not None
    return text


def reasons(world: World) -> list[str]:
    rows = world.api.owner.execute(
        "SELECT reason FROM tenancy.change_log WHERE organization_id = %s AND section = 'reports' "
        "ORDER BY version",
        (world.org,),
    ).fetchall()
    return [str(r["reason"]) for r in rows]


def disposition(name: str) -> str:
    return f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name, safe='')}"


def file_ok(response: Any, content_type: str, name: str) -> bytes:
    assert response.status_code == 200, response.content
    assert response.headers["content-type"] == content_type
    assert response.headers["content-disposition"] == disposition(name)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers.get("x-request-id")
    content: bytes = response.content
    return content


def cell_text(cell: Any, kind: str) -> str | None:
    """What the workbook shows for a JSON cell: a date as its serial, a number as itself."""
    if cell is None:
        return None
    if kind == "date":
        return str((date.fromisoformat(cell) - SERIAL_EPOCH).days)
    if isinstance(cell, bool) or not isinstance(cell, int | float):
        return str(cell)
    return str(Decimal(str(cell)).normalize()) if cell else "0"


def same_rows(book: Workbook, table: dict[str, Any]) -> None:
    """The workbook's data rows are the report's rows, cell for cell, under its header."""
    kinds = [c["kind"] for c in table["columns"]]
    width = len(kinds)
    assert book.row(HEADER_ROW, width) == [c["label"] for c in table["columns"]]
    for offset, row in enumerate(table["rows"]):
        shown = book.row(FIRST_DATA_ROW + offset, width)
        for index, (cell, kind) in enumerate(zip(row, kinds, strict=True)):
            expected = cell_text(cell, kind)
            if expected is None:
                assert shown[index] is None, (offset, index)
            elif kind in ("text", "vehicle", "date"):
                assert shown[index] == expected, (offset, index)
            else:
                assert shown[index] is not None and Decimal(shown[index]) == Decimal(expected)
    after = f"A{FIRST_DATA_ROW + len(table['rows'])}"
    if any(c["sum"] for c in table["columns"]):
        assert book.text(after) == (
            f"{len(table['rows'])} rows" if len(table["rows"]) != 1 else "1 row"
        )
    else:
        assert not book.has(after)
    assert not book.has_formulas


# --- the catalogue and a report page ---


async def test_the_catalogue_reads_in_wire_order_by_right(world: World) -> None:
    response, count = await statements(get(world, world.owner, "/reports"))
    access = ok(response)
    assert count <= 2
    assert list(access) == ACCESS_KEYS
    assert access["businessDate"] == TODAY
    assert access["fleet"] == [*FLEET_REPORTS, "investment"]
    assert access["pettyCash"] == PETTY_REPORTS
    assert [list(h) for h in access["holders"]] == [HOLDER_KEYS, HOLDER_KEYS]
    assert [h["name"] for h in access["holders"]] == ["Antony Maina", "Wanjiru Kamau"]
    assert access["holders"][1]["id"] == str(world.clerk.user_id)
    assert access["canExport"] is True

    clerk = ok(await get(world, world.clerk, "/reports"))
    assert (clerk["fleet"], clerk["pettyCash"], clerk["holders"], clerk["canExport"]) == (
        FLEET_REPORTS,
        [],
        [],
        False,
    )
    problem(await get(world, world.teller, "/reports"), 403, FORBIDDEN)
    assert (await get(world, None, "/reports")).status_code == 401


async def test_a_fleet_report_reads_in_wire_order_with_its_page_and_search(world: World) -> None:
    response, count = await statements(get(world, world.owner, f"/reports/fleet/net?{PERIOD}"))
    net = ok(response)
    assert count <= 2
    assert list(net) == TABLE_KEYS
    assert (net["group"], net["report"], net["title"]) == ("fleet", "net", "Net by vehicle")
    assert (net["from"], net["to"], net["businessDate"]) == ("2026-10-01", TODAY, TODAY)
    assert list(net["headline"]) == FIGURE_KEYS
    assert net["headline"] == {"label": "Net", "value": 14600, "kind": "net"}
    assert [list(f) for f in net["figures"]] == [FIGURE_KEYS] * 3
    assert [list(c) for c in net["columns"]] == [COLUMN_KEYS] * len(net["columns"])
    assert [c["key"] for c in net["columns"]][:3] == ["vehicle", "company", "revenue"]
    assert [c["key"] for c in net["columns"]][-3:] == ["moneyOut", "net", "saved"]
    assert [r[0] for r in net["rows"]] == ["KDA 482M", "KDC 200B", "KDB 111A"]
    assert net["rows"][0][:3] == ["KDA 482M", "North Star", 12700]
    assert net["rows"][0][-3:] == [3300, 9400, 0]
    assert net["rows"][1][-3:] == [4800, 5200, 700]
    assert (net["pageNumber"], net["pageSize"], net["total"]) == (1, 50, 3)
    assert net["totals"][:3] == [None, None, 22700]
    cut = ok(await get(world, world.owner, "/reports/fleet/net?from=2026-10-01&to=2026-10-31"))
    assert cut["to"] == TODAY
    page = ok(await get(world, world.owner, f"/reports/fleet/net?{PERIOD}&page=2&pageSize=1"))
    assert [r[0] for r in page["rows"]] == ["KDC 200B"]
    assert (page["pageNumber"], page["pageSize"], page["total"]) == (2, 1, 3)
    assert page["totals"][2] == 22700
    found = ok(await get(world, world.owner, f"/reports/fleet/net?{PERIOD}&q=kdb"))
    assert (found["total"], [r[0] for r in found["rows"]]) == (1, ["KDB 111A"])
    gaps = ok(await get(world, world.owner, f"/reports/fleet/gaps?{PERIOD}"))
    assert gaps["rows"][0] == ["2026-10-03", "KDA 482M", "North Star", "Revenue not captured"]
    investment = ok(await get(world, world.owner, "/reports/fleet/investment"))
    assert (investment["from"], investment["to"]) == (None, None)
    book = ok(await get(world, world.owner, f"/reports/pettycash/cashBook?{PERIOD}"))
    assert book["headline"] == {"label": "Closing balance", "value": 4000, "kind": "money"}
    assert [r[0] for r in book["rows"]] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    own = ok(
        await get(
            world,
            world.admin,
            f"/reports/pettycash/managers?{PERIOD}&holderId={world.clerk.user_id}",
        )
    )
    assert [r[0] for r in own["rows"]] == ["Wanjiru Kamau"]


async def test_refusals_keep_their_status_and_sentence(world: World) -> None:
    owner, clerk, teller = world.owner, world.clerk, world.teller
    problem(await get(world, owner, f"/reports/fleet/nothing?{PERIOD}"), 404, NOT_FOUND)
    problem(await get(world, owner, f"/reports/pettycash/net?{PERIOD}"), 404, NOT_FOUND)
    problem(
        await get(world, owner, "/reports/fleet/net?from=2026-10-01"),
        400,
        INVALID,
        sentence("report_period_both"),
    )
    problem(
        await get(world, owner, "/reports/fleet/net?from=2026-10-07&to=2026-10-01"),
        400,
        INVALID,
        sentence("report_period_order"),
    )
    problem(
        await get(world, owner, "/reports/fleet/net?from=2025-10-05&to=2026-10-07"),
        400,
        INVALID,
        sentence("report_period_length"),
    )
    problem(
        await get(world, owner, "/reports/fleet/net?from=2026-10-08&to=2026-10-09"),
        400,
        INVALID,
        sentence("report_period_future"),
    )
    problem(
        await get(world, owner, f"/reports/fleet/net?{PERIOD}&q={'x' * 201}"),
        400,
        INVALID,
        sentence("report_search_length"),
    )
    problem(
        await get(world, owner, f"/reports/fleet/net?{PERIOD}&page=0"),
        400,
        INVALID,
        sentence("page_out_of_range"),
    )
    problem(
        await get(world, owner, f"/reports/fleet/net?{PERIOD}&pageSize=101"),
        400,
        INVALID,
        sentence("page_out_of_range"),
    )
    problem(
        await get(world, clerk, "/reports/fleet/investment"),
        403,
        FORBIDDEN,
        sentence("report_investment_permission"),
    )
    problem(
        await get(world, clerk, f"/reports/pettycash/cashBook?{PERIOD}"),
        403,
        FORBIDDEN,
        sentence("report_pettycash_permission"),
    )
    problem(await get(world, clerk, f"/reports/fleet/net/export?{PERIOD}"), 403, FORBIDDEN)
    problem(await get(world, teller, f"/reports/fleet/net?{PERIOD}"), 403, FORBIDDEN)
    problem(await get(world, teller, f"/reports/fleet/net/export?{PERIOD}"), 403, FORBIDDEN)
    problem(
        await get(world, owner, f"/reports/fleet/net/export?{PERIOD}&format=csv"),
        400,
        INVALID,
        sentence("export_format_invalid"),
    )
    problem(
        await get(world, owner, f"/reports/pettycash/cashBook/export?{PERIOD}&holderId={uuid4()}"),
        404,
        NOT_FOUND,
    )
    assert (await get(world, owner, f"/reports/nowhere/net/export?{PERIOD}")).status_code == 404
    assert (await get(world, None, f"/reports/fleet/net/export?{PERIOD}")).status_code == 401
    assert reasons(world) == []


# --- files ---


async def test_an_export_is_a_file_with_its_name_and_one_change_log_row(world: World) -> None:
    net = ok(await get(world, world.owner, f"/reports/fleet/net?{PERIOD}"))
    response, count = await statements(
        get(world, world.owner, f"/reports/fleet/net/export?{PERIOD}")
    )
    content = file_ok(response, XLSX, "Net by vehicle 1 Oct 2026 to 7 Oct 2026.xlsx")
    assert count <= 2
    book = Workbook(content)
    assert book.text("A1") == "Net by vehicle"
    assert "1 Oct 2026 to 7 Oct 2026" in book.text("A2")
    assert book.text("A3") == "Exported 7 Oct 2026 by Antony Maina"
    assert book.text("A5").startswith("NET")
    assert Decimal(book.number("A6")) == Decimal(14600)
    same_rows(book, net)
    assert Decimal(book.number(f"C{FIRST_DATA_ROW + 3}")) == Decimal(22700)
    assert book.sheet_name == "Net by vehicle"

    response = await get(world, world.owner, f"/reports/fleet/net/export?{PERIOD}&format=PDF")
    content = file_ok(response, PDF, "Net by vehicle 1 Oct 2026 to 7 Oct 2026.pdf")
    reader = PdfReader(io.BytesIO(content))
    assert len(reader.pages) == 1
    box = reader.pages[0].mediabox
    assert (round(float(box.width)), round(float(box.height))) == (842, 595)
    assert all(embedded_fonts(reader).values())
    text = reader.pages[0].extract_text()
    assert "Net by vehicle" in text
    assert "KDA 482M" in text
    assert "Page 1 of 1" in text
    assert reader.metadata is not None and reader.metadata.title == "Net by vehicle"

    gaps = ok(await get(world, world.owner, f"/reports/fleet/gaps?{PERIOD}&q=kdb"))
    response = await get(world, world.owner, f"/reports/fleet/gaps/export?{PERIOD}&q=kdb")
    book = Workbook(file_ok(response, XLSX, "Capture gaps 1 Oct 2026 to 7 Oct 2026.xlsx"))
    same_rows(book, gaps)
    assert book.number_format(f"A{FIRST_DATA_ROW}") == "d mmm yyyy"

    response = await get(world, world.owner, "/reports/fleet/investment/export")
    book = Workbook(file_ok(response, XLSX, "Investment.xlsx"))
    assert "As at 7 Oct 2026" in book.text("A2")

    response = await get(
        world,
        world.admin,
        f"/reports/pettycash/cashBook/export?{PERIOD}&holderId={world.clerk.user_id}",
    )
    book = Workbook(file_ok(response, XLSX, "Cash book 1 Oct 2026 to 7 Oct 2026.xlsx"))
    assert "Wanjiru Kamau" in book.text("A2")
    assert reasons(world) == [
        "Exported Net by vehicle for 1 Oct 2026 to 7 Oct 2026 to Excel",
        "Exported Net by vehicle for 1 Oct 2026 to 7 Oct 2026 to PDF",
        'Exported Capture gaps for 1 Oct 2026 to 7 Oct 2026, searched for "kdb" to Excel',
        "Exported Investment to Excel",
        "Exported Cash book for 1 Oct 2026 to 7 Oct 2026 to Excel",
    ]


async def test_a_scoped_viewers_export_holds_no_hidden_vehicle(world: World) -> None:
    set_override(
        world.api.owner,
        Person(world.clerk.user_id, world.org, "", "", "", "", ""),
        "reports.export",
    )
    net = ok(await get(world, world.clerk, f"/reports/fleet/net?{PERIOD}"))
    assert [r[0] for r in net["rows"]] == ["KDA 482M", "KDB 111A"]
    response = await get(world, world.clerk, f"/reports/fleet/net/export?{PERIOD}")
    book = Workbook(file_ok(response, XLSX, "Net by vehicle 1 Oct 2026 to 7 Oct 2026.xlsx"))
    same_rows(book, net)
    assert book.text("A3") == "Exported 7 Oct 2026 by Wanjiru Kamau"
    assert all(book.value(f"A{row}") != "KDC 200B" for row in range(FIRST_DATA_ROW, 20))
    assert Decimal(book.number("A6")) == Decimal(9400)
    response = await get(world, world.clerk, f"/reports/fleet/gaps/export?{PERIOD}&format=pdf")
    content = file_ok(response, PDF, "Capture gaps 1 Oct 2026 to 7 Oct 2026.pdf")
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)
    assert "KDA 482M" in text and "KDC 200B" not in text
    south = ok(
        await get(world, world.clerk, f"/reports/fleet/net?{PERIOD}&companyId={world.south}")
    )
    assert south["rows"] == [] and south["headline"]["value"] == 0


async def test_an_export_past_the_row_bound_is_refused_with_its_sentence(world: World) -> None:
    bulk = add_company(world.api.owner, world.org, "Bulk Line")
    for index in range(28):
        add_vehicle(
            world.api.owner, world.org, bulk, f"KBZ {index:03d}Z", joined_on=date(2025, 10, 1)
        )
    period = "from=2025-10-06&to=2026-10-07"
    gaps = ok(await get(world, world.owner, f"/reports/fleet/gaps?{period}"))
    assert gaps["total"] > 10000
    assert len(gaps["rows"]) == 50
    problem(
        await get(world, world.owner, f"/reports/fleet/gaps/export?{period}"),
        400,
        INVALID,
        sentence("export_too_many_rows", count=f"{gaps['total']:,}"),
    )
    assert reasons(world) == []
    narrowed = ok(await get(world, world.owner, f"/reports/fleet/gaps?{period}&q=KDA"))
    response = await get(world, world.owner, f"/reports/fleet/gaps/export?{period}&q=KDA")
    book = Workbook(file_ok(response, XLSX, "Capture gaps 6 Oct 2025 to 7 Oct 2026.xlsx"))
    same_rows(book, narrowed)


async def test_a_writer_that_fails_after_the_audit_row_leaves_the_row_and_a_retry_writes_one(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The routine commits the rows and the audit row before the file is built (``docs/12``
    2.8): a writer failing then answers a 500 without its message, the row stays for a file
    never delivered, and the retry is a second export with its own row."""

    def broken(self: XlsxWriterAdapter, document: Any) -> bytes:
        raise RuntimeError("disk full at /srv/exports")

    with monkeypatch.context() as patch:
        patch.setattr(XlsxWriterAdapter, "write", broken)
        response = await get(world, world.owner, f"/reports/fleet/net/export?{PERIOD}")
    assert response.status_code == 500
    assert b"disk full" not in response.content and b"/srv/" not in response.content
    exported = "Exported Net by vehicle for 1 Oct 2026 to 7 Oct 2026 to Excel"
    assert reasons(world) == [exported]
    response = await get(world, world.owner, f"/reports/fleet/net/export?{PERIOD}")
    file_ok(response, XLSX, "Net by vehicle 1 Oct 2026 to 7 Oct 2026.xlsx")
    assert reasons(world) == [exported, exported]


# --- the screen exports ---


async def test_screens_export_what_they_list(world: World) -> None:
    owner, admin = world.owner, world.admin
    week = ok(await get(world, owner, "/revenue?weekStart=2026-10-05"))
    response, count = await statements(get(world, owner, "/revenue/export?weekStart=2026-10-05"))
    book = Workbook(file_ok(response, XLSX, "Revenue 5 Oct 2026 to 7 Oct 2026.xlsx"))
    assert count <= 2
    assert book.text("A1") == "Revenue"
    width = 2 + 7 + 3
    assert book.row(HEADER_ROW, width) == [
        "Vehicle",
        "Company",
        "Mon 5",
        "Tue 6",
        "Wed 7",
        "Thu 8",
        "Fri 9",
        "Sat 10",
        "Sun 11",
        "Week total",
        "Target to date",
        "Gap",
    ]
    for offset, vehicle in enumerate(week["vehicles"]):
        shown = book.row(FIRST_DATA_ROW + offset, width)
        assert shown[0] == vehicle["registration"]
        for index, cell in enumerate(vehicle["days"]):
            if cell["status"] == "amount":
                assert shown[2 + index] is not None
                assert Decimal(shown[2 + index]) == Decimal(str(cell["amount"]))
            elif cell["status"] == "missing":
                assert shown[2 + index] == "Missing"
        assert shown[9] is not None and Decimal(shown[9]) == Decimal(str(vehicle["totalAmount"]))
    assert (
        book.text(f"A{FIRST_DATA_ROW + len(week['vehicles'])}") == f"{len(week['vehicles'])} rows"
    )
    kda = next(v for v in week["vehicles"] if v["registration"] == "KDA 482M")
    assert kda["days"][0]["amount"] == 3000
    response = await get(
        world, owner, f"/revenue/export?weekStart=2026-10-05&companyId={world.north}"
    )
    book = Workbook(file_ok(response, XLSX, "Revenue 5 Oct 2026 to 7 Oct 2026.xlsx"))
    assert "North Star" in book.text("A2")
    assert book.value(f"A{FIRST_DATA_ROW + 2}") == "2 rows"
    problem(await get(world, world.teller, "/revenue/export?weekStart=2026-10-05"), 403, FORBIDDEN)
    problem(
        await get(world, owner, "/revenue/export?weekStart=2026-10-05&format=doc"),
        400,
        INVALID,
        sentence("export_format_invalid"),
    )

    listed = ok(await get(world, owner, f"/pettycash/entries?{PERIOD}&kind=expense"))
    response, count = await statements(
        get(world, owner, f"/pettycash/export?{PERIOD}&view=expenses")
    )
    book = Workbook(file_ok(response, XLSX, "Petty cash, expenses 1 Oct 2026 to 7 Oct 2026.xlsx"))
    assert count <= 2
    assert book.row(HEADER_ROW, 10) == [
        "Date",
        "Manager",
        "Vehicle",
        "Item",
        "Units",
        "Unit amount",
        "Amount",
        "Status",
        "Note",
        "Recorded by",
    ]
    assert book.text(f"A{FIRST_DATA_ROW + listed['total']}") == f"{listed['total']} rows"
    assert listed["total"] == 2
    first = book.row(FIRST_DATA_ROW, 10)
    assert first[1:4] == ["Wanjiru Kamau", "KDA 482M", "Tyres"]
    assert first[7] == "Approved"
    assert Decimal(first[6] or "0") == Decimal(3000)
    second = book.row(FIRST_DATA_ROW + 1, 10)
    assert (second[3], second[7], second[8]) == ("Diesel", "Waiting", "=2+2")
    assert book.xf(f"I{FIRST_DATA_ROW + 1}").get("quotePrefix") == "1"
    assert not book.has_formulas
    response = await get(world, owner, f"/pettycash/export?{PERIOD}&view=expenses&status=waiting")
    book = Workbook(file_ok(response, XLSX, "Petty cash, expenses 1 Oct 2026 to 7 Oct 2026.xlsx"))
    assert book.text(f"A{FIRST_DATA_ROW + 1}") == "1 row"
    response = await get(world, owner, f"/pettycash/export?{PERIOD}&view=cash&format=pdf")
    file_ok(response, PDF, "Petty cash, cash received 1 Oct 2026 to 7 Oct 2026.pdf")
    problem(
        await get(world, owner, f"/pettycash/export?{PERIOD}"),
        400,
        INVALID,
        sentence("pettycash_export_view_invalid"),
    )
    problem(await get(world, world.teller, f"/pettycash/export?{PERIOD}&view=cash"), 403, FORBIDDEN)

    ledger = ok(await get(world, admin, f"/expenses/ledger?{PERIOD}"))
    response, count = await statements(get(world, admin, f"/expenses/export?{PERIOD}"))
    book = Workbook(file_ok(response, XLSX, "Central expenses 1 Oct 2026 to 7 Oct 2026.xlsx"))
    assert count <= 2
    assert book.text("A1") == "Central expenses"
    assert book.row(HEADER_ROW, 9) == [
        "Date",
        "Vehicle",
        "Item",
        "Category",
        "Quantity",
        "Unit amount",
        "Amount",
        "Source",
        "Recorded by",
    ]
    assert len(ledger["items"]) == 3
    for offset, item in enumerate(ledger["items"]):
        shown = book.row(FIRST_DATA_ROW + offset, 9)
        assert shown[0] == cell_text(item["date"], "date")
        assert shown[6] is not None and Decimal(shown[6]) == Decimal(str(item["total"]))
    assert book.text(f"A{FIRST_DATA_ROW + 3}") == "3 rows"
    assert book.row(FIRST_DATA_ROW, 9)[7:] == ["Central", "Peter Otieno"]
    problem(await get(world, world.clerk, f"/expenses/export?{PERIOD}"), 403, FORBIDDEN)
    problem(
        await get(world, admin, f"/expenses/export?{PERIOD}&source=nowhere"),
        400,
        INVALID,
        sentence("expense_source_invalid"),
    )
    assert reasons(world) == [
        "Exported Revenue for 5 Oct 2026 to 7 Oct 2026 to Excel",
        "Exported Revenue for 5 Oct 2026 to 7 Oct 2026 to Excel",
        "Exported Petty cash, expenses for 1 Oct 2026 to 7 Oct 2026 to Excel",
        "Exported Petty cash, expenses for 1 Oct 2026 to 7 Oct 2026 to Excel",
        "Exported Petty cash, cash received for 1 Oct 2026 to 7 Oct 2026 to PDF",
        "Exported Central expenses for 1 Oct 2026 to 7 Oct 2026 to Excel",
    ]


# --- the route catalogue ---


OPERATIONS = {
    ("GET", "/setup/reports"): "GetReportsAccess",
    ("GET", "/setup/reports/fleet/{report}"): "GetFleetReport",
    ("GET", "/setup/reports/pettycash/{report}"): "GetPettyCashReport",
    ("GET", "/setup/reports/{group}/{report}/export"): "ExportReport",
}


async def test_every_report_route_has_its_operation_id_and_the_reports_tag() -> None:
    routes = {
        (method, getattr(route, "path", "")): getattr(route, "operation_id", None)
        for route in router.routes
        for method in sorted(getattr(route, "methods", set()))
    }
    assert routes == OPERATIONS
    assert {tag for route in router.routes for tag in getattr(route, "tags", [])} == {"Reports"}
