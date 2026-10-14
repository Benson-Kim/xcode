"""Formula injection through every Excel export (``docs/12-security.md``, bounded exports;
``docs/16-security-matrix.md`` SC3): a company, main category, category, item or schedule
name, a person's name or a note, that starts with ``=``, ``+``, ``-``, ``@``, a tab or a
carriage return is written as a text cell with the quote prefix, never as a formula, in the
Revenue, Central expenses, Petty cash and report files. The names are stored as
``xcode_owner``, as migrated data could hold them, so no input trimming hides a lead.

The business date is 7 Oct 2026 (the test clock in Nairobi)."""

from __future__ import annotations

import dataclasses
import re
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from psycopg.types.json import Jsonb

from xcode_api.domain.reports import CellKind, ReportColumn, ReportFigure
from xcode_api.infra.exports.xlsx import XlsxWriterAdapter

from ..support.client import ApiFactory, AuthApi
from ..support.export_files import NS, Workbook
from ..support.scenario import call
from ..support.setup_client import Member, join
from ..support.setup_rows import (
    Version,
    add_category,
    add_item,
    add_main_category,
    add_record,
    add_schedule,
)
from ..support.tenancy import add_company, add_vehicle, set_scope
from ..unit.test_export_files import COLUMNS, document

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PERIOD = "from=2026-10-01&to=2026-10-07"
LEADS = ("=", "+", "-", "@", "\t", "\r")
COMPANY = "@North Star"
MAIN = "-Running"
CATEGORY = "+Repairs"
ITEM = '=HYPERLINK("http://example.invalid","open")'
SCHEDULE = "\r=1+1 Parking"
PETTY_NOTE = "\t=2+2"
HOLDER = ("=cmd|' /C calc'!A0", "Kamau")
_ESCAPED = re.compile(r"_x([0-9A-Fa-f]{4})_")


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


def _routine(api: AuthApi, name: str, who: Member, org: UUID, *args: Any) -> Any:
    return call(api.owner, name, who.user_id, org, "req-seed", *args, api.clock.now())


async def _seed(api: AuthApi) -> Member:
    owner = await join(api, email="o@example.com", phone="0711000411", role="Owner")
    holder = await join(api, email="h@example.com", phone="0733000411", role="Fleet manager")
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    org = UUID(str(row["id"]))
    for member in (owner, holder):
        set_scope(api.owner, member.user_id, org, all_companies=True)
    api.owner.execute(
        "UPDATE tenancy.memberships SET first_name = %s, last_name = %s WHERE user_id = %s",
        (*HOLDER, holder.user_id),
    )
    company = add_company(api.owner, org, COMPANY)
    kda = add_vehicle(api.owner, org, company, "KDA 482M", joined_on=date(2026, 9, 1))
    for day in (1, 2, 5, 6):
        add_record(api.owner, org, kda, date(2026, 10, day), 4000, recorder=owner.user_id)
    main = add_main_category(api.owner, org, MAIN)
    category = add_category(api.owner, org, CATEGORY, bucket=1, main_category=main)
    item = add_item(api.owner, org, category, ITEM)
    add_schedule(
        api.owner,
        org,
        Version(date(2026, 10, 1), {kda: 300}, name=SCHEDULE, kind=1, frequency=1, day=None),
    )
    _routine(
        api, "pettycash_entry_create", owner, org, None, "cash", date(2026, 10, 1),
        Decimal(10000), holder.user_id, None, None, None, None, None, False, None,
    )  # fmt: skip
    _routine(
        api, "pettycash_entry_create", holder, org, None, "expense", date(2026, 10, 2),
        Decimal(1500), None, kda, item, Decimal(1), None, None, False, None,
    )  # fmt: skip
    api.owner.execute(
        "UPDATE pettycash.entries SET note = %s WHERE organization_id = %s AND kind = 2",
        (PETTY_NOTE, org),
    )
    _routine(
        api, "expenses_entry_create", owner, org, None, date(2026, 10, 6), item, Decimal(2),
        Decimal(1200), None, Jsonb([{"vehicle_id": str(kda), "amount": "2400"}]),
    )  # fmt: skip
    return owner


def _texts(book: Workbook) -> list[tuple[str, str]]:
    """Every string cell as (reference, text), with Excel's ``_xHHHH_`` escapes decoded."""
    cells = []
    for cell in book.sheet.iterfind(".//m:c", NS):
        reference = cell.get("r", "")
        if cell.get("t") in ("s", "inlineStr"):
            raw = book.text(reference)
            cells.append((reference, _ESCAPED.sub(lambda m: chr(int(m.group(1), 16)), raw)))
    return cells


async def _export(api: AuthApi, owner: Member, path: str) -> list[str]:
    response = await api.client.get(f"/setup{path}", headers=owner.headers)
    assert response.status_code == 200, response.content
    assert response.headers["content-type"] == XLSX
    book = Workbook(response.content)
    assert not book.has_formulas
    texts = _texts(book)
    unguarded = [
        (reference, text)
        for reference, text in texts
        if text.startswith(LEADS) and book.xf(reference).get("quotePrefix") != "1"
    ]
    assert unguarded == [], path
    return [text for _, text in texts]


def test_the_bands_figure_labels_and_headers_keep_a_leading_formula_character_as_text() -> None:
    """The organization's display name opens the subtitle and a main category names a figure:
    neither is a data cell, and both keep the quote prefix."""
    columns = (ReportColumn("item", "@Item", CellKind.TEXT, False), *COLUMNS[1:])
    leading = dataclasses.replace(
        document(title="=Net"),
        organization="+Metro Trans",
        headline=ReportFigure("-Net", document().headline.value, CellKind.NET),
        figures=(ReportFigure("	=Running", document().figures[0].value, CellKind.MONEY),),
        columns=columns,
    )
    book = Workbook(XlsxWriterAdapter().write(leading))
    assert not book.has_formulas
    texts = dict(_texts(book))
    for reference in ("A1", "A2", "A5", "B5", "A8"):
        assert texts[reference].startswith(LEADS), (reference, texts[reference])
        assert book.xf(reference).get("quotePrefix") == "1", (reference, texts[reference])


@pytest.mark.asyncio(loop_scope="session")
async def test_no_export_turns_a_leading_formula_character_into_a_formula(api: AuthApi) -> None:
    owner = await _seed(api)
    revenue = await _export(api, owner, "/revenue/export?weekStart=2026-10-05")
    central = await _export(api, owner, f"/expenses/export?{PERIOD}")
    petty = await _export(api, owner, f"/pettycash/export?{PERIOD}&view=expenses")
    money_out = await _export(api, owner, f"/reports/fleet/moneyOut/export?{PERIOD}")
    assert COMPANY in revenue
    assert {ITEM, CATEGORY, SCHEDULE} <= set(central)
    assert {ITEM, PETTY_NOTE, " ".join(HOLDER)} <= set(petty)
    assert ITEM in money_out
    shown = {text[0] for text in revenue + central + petty + money_out if text}
    assert set(LEADS) <= shown
