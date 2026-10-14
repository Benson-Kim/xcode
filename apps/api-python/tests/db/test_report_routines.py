"""The report routines (``api.report_catalog_get``, ``api.report_get``, ``api.report_export_get``
and the three screen exports), called as ``xcode_app``, and the helpers under ``reports``,
called as the owner: the catalogue by right, the checks in their order, each builder's figures
against a fleet whose numbers are worked out here by hand (and Net by vehicle against each
vehicle's own report), the scope of a viewer who sees one company, the floats a petty-cash
report may be cut to, the page and the search, the period cut to the business date, the
export's document and its one change-log row, and the screen exports listing what their
screens list.

The business date is 9 Oct 2026 (a Friday). Antony Maina owns the organization, Peter Otieno
(Office admin) reviews petty cash and records central expenses, Wanjiru Kamau (Fleet manager,
North Star only) keeps a float, Grace Njeri (Revenue clerk) may open no report."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from ..support.scenario import T0, Conn
from ..support.setup_rows import (
    Version,
    add_category,
    add_investment,
    add_item,
    add_main_category,
    add_record,
    add_schedule,
    add_target,
    change_rows,
    read,
    refuses,
)
from ..support.tenancy import (
    Member,
    add_company,
    add_vehicle,
    audit_events,
    provision_member,
    set_override,
    set_scope,
)

TODAY = date(2026, 10, 9)
FIRST = date(2026, 10, 1)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FLEET_REPORTS = ["net", "target", "moneyOut", "gaps", "savings"]
PETTY_REPORTS = ["cashBook", "managers", "vehicles", "items", "waiting", "sentBack", "rejected"]
REVIEWER = (
    "pettycash.view",
    "pettycash.view_all",
    "pettycash.reports",
    "pettycash.export",
    "pettycash.approve_item",
)


def oct(day: int) -> date:
    return date(2026, 10, day)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def num(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def nums(cells: list[Any]) -> list[Decimal | None]:
    return [num(c) if isinstance(c, int | float) else c for c in cells]


def keys(table: dict[str, Any]) -> list[str]:
    return [str(c["key"]) for c in table["columns"]]


def figure(table: dict[str, Any], label: str) -> Decimal | None:
    [found] = [f for f in table["figures"] if f["label"] == label]
    return num(found["value"])


def detail(error: psycopg.Error) -> dict[str, Any]:
    text = error.diag.message_detail
    return json.loads(text) if text else {}


@dataclass(frozen=True, slots=True)
class Fleet:
    owner: Member
    admin: Member
    clerk: Member
    teller: Member
    north: UUID
    south: UUID
    kda: UUID
    kdb: UUID
    kdc: UUID
    running: UUID
    tyres: UUID
    diesel: UUID
    approved: dict[str, Any]
    waiting: dict[str, Any]

    @property
    def org(self) -> UUID:
        return self.owner.org


def entry(
    app: Conn,
    who: Member,
    kind: str,
    on: date,
    amount: Any,
    *,
    holder: UUID | None = None,
    vehicle: UUID | None = None,
    item: UUID | None = None,
    units: Any = None,
    payee: str | None = None,
    note: str | None = None,
    now: datetime = T0,
) -> dict[str, Any]:
    saved: dict[str, Any] = read(
        app,
        "pettycash_entry_create",
        who,
        None,
        kind,
        on,
        num(amount),
        holder,
        vehicle,
        item,
        num(units),
        payee,
        note,
        False,
        None,
        now=now,
    )
    return saved


@pytest.fixture
def fleet(operator_conn: Conn, owner_conn: Conn, app_conn: Conn) -> Fleet:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    admin = provision_member(operator_conn, 2, "Office admin", "Peter", "Otieno")
    clerk = provision_member(operator_conn, 3, "Fleet manager", "Wanjiru", "Kamau")
    teller = provision_member(operator_conn, 4, "Revenue clerk", "Grace", "Njeri")
    org = owner.org
    north = add_company(owner_conn, org, "North Star")
    south = add_company(owner_conn, org, "South Line")
    kda = add_vehicle(owner_conn, org, north, "KDA 482M", joined_on=oct(1))
    kdb = add_vehicle(owner_conn, org, north, "KDB 111A", joined_on=oct(5))
    kdc = add_vehicle(owner_conn, org, south, "KDC 200B", joined_on=date(2026, 9, 1))
    for member in (owner, admin, teller):
        set_scope(owner_conn, member, org, all_companies=True)
    set_scope(owner_conn, clerk, org, companies=[north])
    for permission in REVIEWER:
        set_override(owner_conn, admin, permission)
    owner_conn.execute(
        "UPDATE tenancy.memberships SET approval_limit = 5000 "
        "WHERE organization_id = %s AND user_id = %s",
        (org, admin.id),
    )
    owner_conn.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = 'days', back_limit_count = 30 "
        "WHERE organization_id = %s",
        (org,),
    )
    add_target(owner_conn, org, kda, 1, oct(1), 7000)
    add_target(owner_conn, org, kdb, 1, oct(5), 3500)
    add_target(owner_conn, org, kdc, 1, date(2026, 9, 1), 7000)
    add_record(owner_conn, org, kda, oct(1), 4500, recorder=owner.id)
    add_record(owner_conn, org, kda, oct(2), 5200, recorder=owner.id)
    add_record(owner_conn, org, kda, oct(3), None, recorder=owner.id, reason=1)
    add_record(owner_conn, org, kdb, oct(5), 3000, recorder=owner.id)
    for day in range(1, 8):
        add_record(owner_conn, org, kdc, oct(day), 2000, recorder=owner.id)
    running = add_main_category(owner_conn, org, "Running")
    repairs = add_category(owner_conn, org, "Repairs", bucket=1, main_category=running)
    tyres = add_item(owner_conn, org, repairs, "Tyres")
    fuelling = add_category(owner_conn, org, "Fuelling", bucket=None)
    diesel = add_item(owner_conn, org, fuelling, "Diesel")
    add_schedule(
        owner_conn,
        org,
        Version(oct(1), {kda: 300}, name="Parking", kind=1, frequency=3, day=5, bucket=2),
    )
    add_schedule(
        owner_conn,
        org,
        Version(oct(1), {kdc: 100}, name="Tyre fund", kind=2, frequency=1, day=None),
    )
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET initial_investment = 500000 WHERE id = %s", (kda,)
    )
    add_investment(owner_conn, org, kda, oct(2), "Engine", 100000, recorder=owner.id)
    entry(app_conn, owner, "cash", oct(1), 10000, holder=clerk.id, now=at(1))
    approved = entry(
        app_conn, clerk, "expense", oct(2), 1500, vehicle=kda, item=tyres, units=2, now=at(2)
    )
    approved = read(
        app_conn,
        "pettycash_entry_approve",
        admin,
        UUID(approved["id"]),
        approved["version"],
        now=at(3),
    )
    waiting = entry(
        app_conn, clerk, "expense", oct(3), 3000, vehicle=kda, item=diesel, units=1, now=at(4)
    )
    entry(app_conn, owner, "credit", oct(4), 500, holder=clerk.id, note="Paid back", now=at(5))
    read(
        app_conn,
        "expenses_entry_create",
        admin,
        None,
        oct(6),
        tyres,
        Decimal(4),
        Decimal(1200),
        None,
        Jsonb([{"vehicle_id": str(kdc), "amount": "4800"}]),
        now=at(6),
    )
    return Fleet(
        owner,
        admin,
        clerk,
        teller,
        north,
        south,
        kda,
        kdb,
        kdc,
        running,
        tyres,
        diesel,
        approved,
        waiting,
    )


def report(
    app: Conn,
    who: Member,
    group: str,
    name: str,
    first: date | None = FIRST,
    last: date | None = TODAY,
    *,
    company: UUID | None = None,
    holder: UUID | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 50,
) -> dict[str, Any]:
    table: dict[str, Any] = read(
        app, "report_get", who, group, name, first, last, company, holder, q, page, size
    )
    return table


def report_refused(
    app: Conn, who: Member, args: list[Any], sqlstate: str, code: str
) -> dict[str, Any]:
    return detail(refuses(app, "report_get", who, args, sqlstate, code))


def export(
    app: Conn,
    who: Member,
    group: str,
    name: str,
    first: date | None = FIRST,
    last: date | None = TODAY,
    *,
    company: UUID | None = None,
    holder: UUID | None = None,
    q: str | None = None,
    fmt: str | None = None,
    now: datetime = T0,
) -> dict[str, Any]:
    document: dict[str, Any] = read(
        app, "report_export_get", who, group, name, first, last, company, holder, q, fmt, now=now
    )
    return document


def helper(owner: Conn, expression: str, *args: Any) -> Any:
    row = owner.execute(f"SELECT {expression} AS r", args).fetchone()
    assert row is not None
    return row["r"]


def helper_refused(
    owner: Conn, expression: str, args: tuple[Any, ...], code: str
) -> dict[str, Any]:
    with pytest.raises(psycopg.Error) as caught:
        owner.execute(f"SELECT {expression} AS r", args).fetchall()
    assert caught.value.sqlstate == "XC422"
    assert caught.value.diag.message_primary == code
    return detail(caught.value)


def row_of(table: dict[str, Any], registration: str) -> list[Any]:
    [found] = [r for r in table["rows"] if r[0] == registration]
    return list(found)


# --- the catalogue and the rights ---


def test_the_catalogue_lists_what_the_actor_may_open(app_conn: Conn, fleet: Fleet) -> None:
    owner = read(app_conn, "report_catalog_get", fleet.owner)
    assert owner["business_date"] == "2026-10-09"
    assert owner["first_day_of_week"] in range(7)
    assert owner["fleet"] == [*FLEET_REPORTS, "investment"]
    assert owner["petty_cash"] == PETTY_REPORTS
    assert [h["name"] for h in owner["holders"]] == ["Antony Maina", "Wanjiru Kamau"]
    assert owner["holders"][1] == {
        "id": str(fleet.clerk.id),
        "name": "Wanjiru Kamau",
        "active": True,
    }
    assert owner["can_export"] is True

    clerk = read(app_conn, "report_catalog_get", fleet.clerk)
    assert clerk["fleet"] == FLEET_REPORTS
    assert clerk["petty_cash"] == []
    assert clerk["holders"] == []
    assert clerk["can_export"] is False


def test_a_holder_with_the_reports_right_sees_their_own_float_only(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    set_override(owner_conn, fleet.clerk, "pettycash.reports")
    clerk = read(app_conn, "report_catalog_get", fleet.clerk)
    assert clerk["petty_cash"] == PETTY_REPORTS
    assert [h["id"] for h in clerk["holders"]] == [str(fleet.clerk.id)]
    admin = read(app_conn, "report_catalog_get", fleet.admin)
    assert [h["id"] for h in admin["holders"]] == [str(fleet.owner.id), str(fleet.clerk.id)]


def test_each_report_and_export_refuses_without_its_right(app_conn: Conn, fleet: Fleet) -> None:
    teller = fleet.teller
    refuses(app_conn, "report_catalog_get", teller, [], "XC403", "permission_missing")
    report_refused(
        app_conn,
        teller,
        ["fleet", "net", FIRST, TODAY, None, None, None, 1, 50],
        "XC403",
        "permission_missing",
    )
    refuses(
        app_conn,
        "report_export_get",
        teller,
        ["fleet", "net", FIRST, TODAY, None, None, None, None],
        "XC403",
        "permission_missing",
    )
    refuses(
        app_conn, "revenue_export_get", teller, [oct(5), None, None], "XC403", "permission_missing"
    )
    refuses(
        app_conn,
        "expenses_export_get",
        teller,
        [FIRST, TODAY, None, None, None],
        "XC403",
        "permission_missing",
    )
    refuses(
        app_conn,
        "pettycash_export_get",
        teller,
        [FIRST, TODAY, None, "expenses", None, None, None],
        "XC403",
        "permission_missing",
    )
    clerk = fleet.clerk
    refuses(
        app_conn,
        "report_export_get",
        clerk,
        ["fleet", "net", FIRST, TODAY, None, None, None, None],
        "XC403",
        "permission_missing",
    )
    report_refused(
        app_conn,
        clerk,
        ["fleet", "investment", None, None, None, None, None, 1, 50],
        "XC403",
        "report_investment_permission",
    )
    report_refused(
        app_conn,
        clerk,
        ["pettycash", "cashBook", FIRST, TODAY, None, None, None, 1, 50],
        "XC403",
        "report_pettycash_permission",
    )
    refuses(
        app_conn,
        "expenses_export_get",
        clerk,
        [FIRST, TODAY, None, None, None],
        "XC403",
        "permission_missing",
    )


def test_the_report_checks_run_in_their_order(app_conn: Conn, fleet: Fleet) -> None:
    owner = fleet.owner
    long = "x" * 201
    bad = ["fleet", "nothing", None, None, None, None, long, 0, 50]
    report_refused(app_conn, owner, bad, "XC422", "page_out_of_range")
    bad[7] = 1
    report_refused(app_conn, owner, bad, "XC422", "report_search_length")
    bad[6] = None
    report_refused(app_conn, owner, bad, "XC404", "not_found")
    report_refused(
        app_conn,
        owner,
        ["nowhere", "net", FIRST, TODAY, None, None, None, 1, 50],
        "XC404",
        "not_found",
    )
    net = ["fleet", "net", None, TODAY, None, None, None, 1, 50]
    report_refused(app_conn, owner, net, "XC422", "report_period_both")
    net[2], net[3] = TODAY, FIRST
    report_refused(app_conn, owner, net, "XC422", "report_period_order")
    net[2], net[3] = date(2025, 10, 7), TODAY
    report_refused(app_conn, owner, net, "XC422", "report_period_length")
    net[2], net[3] = oct(10), oct(11)
    report_refused(app_conn, owner, net, "XC422", "report_period_future")
    assert report(app_conn, owner, "fleet", "net", date(2025, 10, 8), TODAY)["total"] == 3

    bad = ["fleet", "nothing", None, None, None, None, long, "csv"]
    refuses(app_conn, "report_export_get", owner, bad, "XC422", "export_format_invalid")
    bad[7] = "xlsx"
    refuses(app_conn, "report_export_get", owner, bad, "XC422", "report_search_length")
    bad[6] = None
    refuses(app_conn, "report_export_get", owner, bad, "XC404", "not_found")


def test_a_dated_report_is_cut_to_the_business_date_and_an_undated_one_has_no_period(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    net = report(app_conn, fleet.owner, "fleet", "net", FIRST, oct(20))
    assert (net["from_date"], net["to_date"], net["business_date"]) == (
        "2026-10-01",
        "2026-10-09",
        "2026-10-09",
    )
    investment = report(app_conn, fleet.owner, "fleet", "investment", None, None)
    assert (investment["from_date"], investment["to_date"]) == (None, None)
    assert investment["business_date"] == "2026-10-09"
    assert investment["title"] == "Investment"
    period = helper(owner_conn, "reports.check_period(%s, %s, %s)", FIRST, oct(20), TODAY)
    assert period.lower == FIRST
    assert TODAY in period
    assert oct(10) not in period


# --- the fleet builders ---


def test_net_by_vehicle_agrees_with_each_vehicle_report_and_splits_money_out_by_main_category(
    app_conn: Conn, fleet: Fleet
) -> None:
    net = report(app_conn, fleet.owner, "fleet", "net")
    assert net["title"] == "Net by vehicle"
    assert keys(net) == [
        "vehicle",
        "company",
        "revenue",
        f"main:{fleet.running}",
        "main:none",
        "moneyOut",
        "net",
        "saved",
    ]
    assert [c["label"] for c in net["columns"]][3:5] == ["Running", "No main category"]
    assert [r[0] for r in net["rows"]] == ["KDC 200B", "KDA 482M", "KDB 111A"]
    assert nums(row_of(net, "KDA 482M")) == [
        "KDA 482M",
        "North Star",
        Decimal(9700),
        Decimal(3000),
        Decimal(300),
        Decimal(3300),
        Decimal(6400),
        Decimal(0),
    ]
    assert nums(row_of(net, "KDC 200B")) == [
        "KDC 200B",
        "South Line",
        Decimal(14000),
        Decimal(4800),
        Decimal(0),
        Decimal(4800),
        Decimal(9200),
        Decimal(900),
    ]
    assert nums(row_of(net, "KDB 111A")) == [
        "KDB 111A",
        "North Star",
        Decimal(3000),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(3000),
        Decimal(0),
    ]
    assert (net["headline"]["label"], num(net["headline"]["value"])) == ("Net", Decimal(18600))
    assert figure(net, "Revenue") == Decimal(26700)
    assert figure(net, "Money out") == Decimal(8100)
    assert figure(net, "Saved") == Decimal(900)
    assert nums(net["totals"]) == [
        None,
        None,
        Decimal(26700),
        Decimal(7800),
        Decimal(300),
        Decimal(8100),
        Decimal(18600),
        Decimal(900),
    ]
    for registration, vehicle in (
        ("KDA 482M", fleet.kda),
        ("KDB 111A", fleet.kdb),
        ("KDC 200B", fleet.kdc),
    ):
        own = read(app_conn, "setup_vehicle_report", fleet.owner, vehicle, None, FIRST, TODAY)
        row = row_of(net, registration)
        assert num(own["money_in"]) == num(row[2])
        assert num(own["money_out"]) == num(row[5])
        assert num(own["net"]) == num(row[6])
        assert num(own["savings"]) == num(row[7])


def test_revenue_against_target_counts_captured_no_revenue_and_missing_days(
    app_conn: Conn, fleet: Fleet
) -> None:
    target = report(app_conn, fleet.owner, "fleet", "target")
    assert target["title"] == "Revenue against target"
    assert keys(target) == [
        "vehicle",
        "company",
        "captured",
        "noRevenue",
        "missing",
        "revenue",
        "target",
        "reached",
        "against",
    ]
    assert [nums(r) for r in target["rows"]] == [
        [
            "KDA 482M",
            "North Star",
            2,
            1,
            5,
            Decimal(9700),
            Decimal(8000),
            Decimal("121.3"),
            Decimal(1700),
        ],
        [
            "KDB 111A",
            "North Star",
            1,
            0,
            3,
            Decimal(3000),
            Decimal(2000),
            Decimal("150.0"),
            Decimal(1000),
        ],
        [
            "KDC 200B",
            "South Line",
            7,
            0,
            1,
            Decimal(14000),
            Decimal(8000),
            Decimal("175.0"),
            Decimal(6000),
        ],
    ]
    assert num(target["headline"]["value"]) == Decimal(26700)
    assert figure(target, "Target") == Decimal(18000)
    assert figure(target, "Reached") == Decimal("148.3")
    assert figure(target, "Missing days") == Decimal(9)
    assert nums(target["totals"]) == [
        None,
        None,
        10,
        1,
        9,
        Decimal(26700),
        Decimal(18000),
        None,
        Decimal(8700),
    ]


def test_capture_gaps_lists_each_missing_day_in_order(app_conn: Conn, fleet: Fleet) -> None:
    gaps = report(app_conn, fleet.owner, "fleet", "gaps")
    assert gaps["title"] == "Capture gaps"
    assert keys(gaps) == ["date", "vehicle", "company", "missing"]
    assert [(r[0], r[1]) for r in gaps["rows"]] == [
        ("2026-10-04", "KDA 482M"),
        ("2026-10-05", "KDA 482M"),
        ("2026-10-06", "KDA 482M"),
        ("2026-10-06", "KDB 111A"),
        ("2026-10-07", "KDA 482M"),
        ("2026-10-07", "KDB 111A"),
        ("2026-10-08", "KDA 482M"),
        ("2026-10-08", "KDB 111A"),
        ("2026-10-08", "KDC 200B"),
    ]
    assert gaps["rows"][-1] == ["2026-10-08", "KDC 200B", "South Line", "Revenue not captured"]
    assert num(gaps["headline"]["value"]) == Decimal(9)
    assert figure(gaps, "Vehicles with gaps") == Decimal(3)
    south = report(app_conn, fleet.owner, "fleet", "gaps", company=fleet.south)
    assert [r[1] for r in south["rows"]] == ["KDC 200B"]
    later = report(app_conn, fleet.owner, "fleet", "gaps", oct(7), TODAY)
    assert len(later["rows"]) == 5


def test_money_out_groups_every_source_by_item_at_the_true_unit_cost(
    app_conn: Conn, fleet: Fleet
) -> None:
    money_out = report(app_conn, fleet.owner, "fleet", "moneyOut")
    assert money_out["title"] == "Money out"
    assert keys(money_out) == [
        "mainCategory",
        "category",
        "item",
        "entries",
        "quantity",
        "low",
        "high",
        "amount",
        "share",
    ]
    tyres, parking = (nums(r) for r in money_out["rows"])
    assert tyres == [
        "Running",
        "Repairs",
        "Tyres",
        2,
        Decimal(6),
        Decimal(1200),
        Decimal(1500),
        Decimal(7800),
        Decimal("96.3"),
    ]
    assert parking[:4] == ["Not set", "recurring charges", "Parking", 1]
    assert parking[7:] == [Decimal(300), Decimal("3.7")]
    assert num(money_out["headline"]["value"]) == Decimal(8100)
    assert [(f["label"], num(f["value"])) for f in money_out["figures"]] == [
        ("Running", Decimal(7800)),
        ("No main category", Decimal(300)),
    ]
    assert nums(money_out["totals"])[3] == 3
    assert nums(money_out["totals"])[7] == Decimal(8100)


def test_savings_count_runs_in_the_period_and_the_balance_since_each_saving_began(
    app_conn: Conn, fleet: Fleet
) -> None:
    savings = report(app_conn, fleet.owner, "fleet", "savings")
    assert savings["title"] == "Savings"
    assert keys(savings) == [
        "vehicle",
        "company",
        "savedRuns",
        "skippedRuns",
        "heldRuns",
        "saved",
        "notSaved",
        "balance",
    ]
    assert [nums(r) for r in savings["rows"]] == [
        ["KDC 200B", "South Line", 9, 0, 0, Decimal(900), Decimal(0), Decimal(900)],
    ]
    assert num(savings["headline"]["value"]) == Decimal(900)
    assert figure(savings, "Balance") == Decimal(900)
    assert figure(savings, "Not saved") == Decimal(0)
    assert figure(savings, "Runs skipped") == Decimal(0)
    assert figure(savings, "Waiting for revenue") == Decimal(0)
    later = report(app_conn, fleet.owner, "fleet", "savings", oct(5), TODAY)
    assert [nums(r) for r in later["rows"]] == [
        ["KDC 200B", "South Line", 5, 0, 0, Decimal(500), Decimal(0), Decimal(900)],
    ]
    north = report(app_conn, fleet.owner, "fleet", "savings", company=fleet.north)
    assert north["rows"] == []
    assert num(north["headline"]["value"]) == Decimal(0)


def test_investment_shows_what_came_back_since_joining_and_needs_its_permission(
    app_conn: Conn, fleet: Fleet
) -> None:
    investment = report(app_conn, fleet.owner, "fleet", "investment", None, None)
    assert keys(investment) == ["vehicle", "company", "joined", "invested", "net", "recovered"]
    assert [nums(r) for r in investment["rows"]] == [
        ["KDA 482M", "North Star", "2026-10-01", Decimal(600000), Decimal(6400), Decimal("1.1")],
        ["KDB 111A", "North Star", "2026-10-05", None, Decimal(3000), None],
        ["KDC 200B", "South Line", "2026-09-01", None, Decimal(9200), None],
    ]
    assert (investment["headline"]["label"], num(investment["headline"]["value"])) == (
        "Invested in vehicles",
        Decimal(600000),
    )
    assert figure(investment, "Net since joining") == Decimal(18600)
    assert figure(investment, "Recovered") == Decimal("3.1")
    assert nums(investment["totals"]) == [None, None, None, Decimal(600000), Decimal(18600), None]
    admin = read(app_conn, "report_catalog_get", fleet.admin)
    assert "investment" in admin["fleet"]
    assert len(report(app_conn, fleet.admin, "fleet", "investment", None, None)["rows"]) == 3


def test_a_scoped_viewer_sees_no_hidden_vehicle_in_any_figure(app_conn: Conn, fleet: Fleet) -> None:
    clerk = fleet.clerk
    net = report(app_conn, clerk, "fleet", "net")
    assert [r[0] for r in net["rows"]] == ["KDA 482M", "KDB 111A"]
    assert keys(net) == [
        "vehicle",
        "company",
        "revenue",
        f"main:{fleet.running}",
        "main:none",
        "moneyOut",
        "net",
        "saved",
    ]
    assert num(net["headline"]["value"]) == Decimal(9400)
    assert figure(net, "Revenue") == Decimal(12700)
    assert figure(net, "Money out") == Decimal(3300)
    target = report(app_conn, clerk, "fleet", "target")
    assert [r[0] for r in target["rows"]] == ["KDA 482M", "KDB 111A"]
    assert figure(target, "Missing days") == Decimal(8)
    gaps = report(app_conn, clerk, "fleet", "gaps")
    assert len(gaps["rows"]) == 8 and all(r[1] != "KDC 200B" for r in gaps["rows"])
    money_out = report(app_conn, clerk, "fleet", "moneyOut")
    assert [nums(r)[7] for r in money_out["rows"]] == [Decimal(3000), Decimal(300)]
    assert num(money_out["headline"]["value"]) == Decimal(3300)
    savings = report(app_conn, clerk, "fleet", "savings")
    assert savings["rows"] == []
    south = report(app_conn, clerk, "fleet", "net", company=fleet.south)
    assert south["rows"] == []
    assert num(south["headline"]["value"]) == Decimal(0)


# --- the petty-cash builders ---


def test_petty_cash_reports_follow_the_floats_a_person_may_see(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    book = report(app_conn, fleet.owner, "pettycash", "cashBook")
    assert book["title"] == "Cash book"
    assert keys(book) == ["date", "opening", "cash", "expenses", "credits", "closing", "waiting"]
    assert [nums(r) for r in book["rows"]] == [
        [
            "2026-10-01",
            Decimal(0),
            Decimal(10000),
            Decimal(0),
            Decimal(0),
            Decimal(10000),
            Decimal(0),
        ],
        [
            "2026-10-02",
            Decimal(10000),
            Decimal(0),
            Decimal(3000),
            Decimal(0),
            Decimal(7000),
            Decimal(0),
        ],
        [
            "2026-10-03",
            Decimal(7000),
            Decimal(0),
            Decimal(3000),
            Decimal(0),
            Decimal(4000),
            Decimal(3000),
        ],
        [
            "2026-10-04",
            Decimal(4000),
            Decimal(0),
            Decimal(0),
            Decimal(500),
            Decimal(3500),
            Decimal(0),
        ],
    ]
    assert (book["headline"]["label"], num(book["headline"]["value"])) == (
        "Closing balance",
        Decimal(3500),
    )
    assert figure(book, "Opening balance") == Decimal(0)
    assert figure(book, "Cash received") == Decimal(10000)
    assert figure(book, "Expenses") == Decimal(6000)
    assert figure(book, "Credit notes") == Decimal(500)
    later = report(app_conn, fleet.owner, "pettycash", "cashBook", oct(3), TODAY)
    assert figure(later, "Opening balance") == Decimal(7000)
    assert [nums(r)[1] for r in later["rows"]] == [Decimal(7000), Decimal(4000)]

    managers = report(app_conn, fleet.owner, "pettycash", "managers")
    assert keys(managers) == [
        "manager",
        "cashReceived",
        "expenses",
        "creditNotes",
        "waiting",
        "rejected",
        "balance",
    ]
    assert [nums(r) for r in managers["rows"]] == [
        [
            "Wanjiru Kamau",
            Decimal(10000),
            Decimal(6000),
            Decimal(500),
            Decimal(3000),
            Decimal(0),
            Decimal(3500),
        ],
    ]

    waiting = report(app_conn, fleet.owner, "pettycash", "waiting", None, None)
    assert keys(waiting) == [
        "date",
        "manager",
        "vehicle",
        "item",
        "amount",
        "daysWaiting",
        "recordedBy",
    ]
    assert [nums(r) for r in waiting["rows"]] == [
        ["2026-10-03", "Wanjiru Kamau", "KDA 482M", "Diesel", Decimal(3000), 6, "Wanjiru Kamau"],
    ]
    assert num(waiting["headline"]["value"]) == Decimal(3000)
    assert (waiting["from_date"], waiting["to_date"]) == (None, None)

    items = report(app_conn, fleet.owner, "pettycash", "items")
    assert [nums(r) for r in items["rows"]] == [
        ["Fuelling", "Diesel", 1, Decimal(1), Decimal(3000)],
        ["Repairs", "Tyres", 1, Decimal(2), Decimal(3000)],
    ]
    vehicles = report(app_conn, fleet.owner, "pettycash", "vehicles")
    assert [nums(r) for r in vehicles["rows"]] == [
        ["KDA 482M", "North Star", 2, Decimal(3000), Decimal(3000), Decimal(6000)],
    ]
    assert report(app_conn, fleet.owner, "pettycash", "sentBack")["rows"] == []
    assert report(app_conn, fleet.owner, "pettycash", "rejected")["rows"] == []

    for_admin = report(app_conn, fleet.admin, "pettycash", "cashBook", holder=fleet.clerk.id)
    assert for_admin["rows"] == book["rows"]
    report_refused(
        app_conn,
        fleet.admin,
        ["pettycash", "cashBook", FIRST, TODAY, None, uuid4(), None, 1, 50],
        "XC404",
        "not_found",
    )
    report_refused(
        app_conn,
        fleet.admin,
        ["pettycash", "cashBook", FIRST, TODAY, None, fleet.admin.id, None, 1, 50],
        "XC404",
        "not_found",
    )


def test_a_petty_cash_report_of_another_float_is_not_found(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    set_override(owner_conn, fleet.clerk, "pettycash.reports")
    set_override(owner_conn, fleet.admin, "pettycash.spend")
    own = report(app_conn, fleet.clerk, "pettycash", "managers")
    assert [r[0] for r in own["rows"]] == ["Wanjiru Kamau"]
    chosen = report(app_conn, fleet.clerk, "pettycash", "managers", holder=fleet.clerk.id)
    assert chosen["rows"] == own["rows"]
    entry(app_conn, fleet.owner, "cash", oct(2), 2000, holder=fleet.admin.id, now=at(7))
    report_refused(
        app_conn,
        fleet.clerk,
        ["pettycash", "managers", FIRST, TODAY, None, fleet.admin.id, None, 1, 50],
        "XC404",
        "not_found",
    )
    every = report(app_conn, fleet.owner, "pettycash", "managers")
    assert [r[0] for r in every["rows"]] == ["Peter Otieno", "Wanjiru Kamau"]
    book = report(app_conn, fleet.clerk, "pettycash", "cashBook")
    assert num(book["headline"]["value"]) == Decimal(3500)


# --- the page, the search and the small helpers ---


def test_the_page_cuts_the_matching_rows_and_the_totals_cover_every_match(
    app_conn: Conn, fleet: Fleet
) -> None:
    page = report(app_conn, fleet.owner, "fleet", "net", page=2, size=1)
    assert [r[0] for r in page["rows"]] == ["KDA 482M"]
    assert (page["page_number"], page["page_size"], page["total"]) == (2, 1, 3)
    assert nums(page["totals"])[2] == Decimal(26700)
    found = report(app_conn, fleet.owner, "fleet", "net", q=" kda  9,700 ")
    assert [r[0] for r in found["rows"]] == ["KDA 482M"]
    assert found["total"] == 1
    assert nums(found["totals"])[2] == Decimal(9700)
    assert figure(found, "Revenue") == Decimal(26700)
    none = report(app_conn, fleet.owner, "fleet", "net", q="nothing like it")
    assert (none["rows"], none["total"]) == ([], 0)
    assert len(none["totals"]) == len(none["columns"])
    assert report(app_conn, fleet.owner, "fleet", "net", q="north")["total"] == 2
    gaps = report(app_conn, fleet.owner, "fleet", "gaps", q="2026-10-06")
    assert [(r[0], r[1]) for r in gaps["rows"]] == [
        ("2026-10-06", "KDA 482M"),
        ("2026-10-06", "KDB 111A"),
    ]
    assert report(app_conn, fleet.owner, "fleet", "gaps", q="Oct 2026")["total"] == 9
    assert report(app_conn, fleet.owner, "fleet", "gaps", q="2026-10-06 kdb")["total"] == 1
    assert report(app_conn, fleet.owner, "fleet", "gaps", page=3, size=4)["rows"] == [
        ["2026-10-08", "KDC 200B", "South Line", "Revenue not captured"],
    ]


def test_cell_text_shows_dates_numbers_and_texts_as_the_search_sees_them(owner_conn: Conn) -> None:
    def text(cell: str, kind: str) -> str | None:
        value = helper(owner_conn, "reports.cell_text(%s::jsonb, %s)", cell, kind)
        return None if value is None else str(value)

    assert text('"KDA 482M"', "vehicle") == "KDA 482M"
    assert text('"Revenue not captured"', "text") == "Revenue not captured"
    day = text('"2026-10-06"', "date")
    assert day is not None and "2026-10-06" in day and "6 Oct 2026" in day
    money = text("4500", "money")
    assert money is not None and "4500" in money and "4,500" in money
    cents = text("4500.5", "money")
    assert cents is not None and "4,500.50" in cents
    assert text("null", "money") is None
    assert text("3", "count") is not None


def test_ratio_rounds_half_away_from_zero_and_has_no_answer_for_an_empty_whole(
    owner_conn: Conn,
) -> None:
    def ratio(part: Any, whole: Any) -> Decimal | None:
        return num(helper(owner_conn, "reports.ratio(%s::numeric, %s::numeric)", part, whole))

    assert ratio(1, 3) == Decimal("33.3")
    assert ratio(2, 3) == Decimal("66.7")
    assert ratio(Decimal("0.00125"), 1) == Decimal("0.1")
    assert ratio(-1, 8) == Decimal("-12.5")
    assert ratio(1, 0) is None
    assert ratio(1, None) is None
    assert ratio(None, 5) == Decimal("0.0")


def test_the_period_checks_answer_in_order_and_cut_the_last_day_to_today(owner_conn: Conn) -> None:
    expression = "reports.check_period(%s::date, %s::date, %s::date)"
    helper_refused(owner_conn, expression, (None, TODAY, TODAY), "report_period_both")
    helper_refused(owner_conn, expression, (FIRST, None, TODAY), "report_period_both")
    helper_refused(owner_conn, expression, (TODAY, FIRST, TODAY), "report_period_order")
    helper_refused(
        owner_conn, expression, (date(2025, 10, 7), TODAY, TODAY), "report_period_length"
    )
    helper_refused(owner_conn, expression, (oct(10), oct(11), TODAY), "report_period_future")
    whole = helper(owner_conn, expression, date(2025, 10, 8), TODAY, TODAY)
    assert whole.lower == date(2025, 10, 8) and TODAY in whole
    cut = helper(owner_conn, expression, FIRST, oct(20), TODAY)
    assert cut.lower == FIRST and TODAY in cut and oct(10) not in cut
    one = helper(owner_conn, expression, TODAY, TODAY, TODAY)
    assert TODAY in one and oct(8) not in one


def test_check_export_reads_the_format_in_any_case_and_caps_the_rows(owner_conn: Conn) -> None:
    expression = "reports.check_export(%s::text, %s::integer)"
    assert helper(owner_conn, expression, None, None) == "xlsx"
    assert helper(owner_conn, expression, "  ", None) == "xlsx"
    assert helper(owner_conn, expression, " XLSX ", 10000) == "xlsx"
    assert helper(owner_conn, expression, "Pdf", 0) == "pdf"
    helper_refused(owner_conn, expression, ("csv", 1), "export_format_invalid")
    assert helper_refused(owner_conn, expression, ("xlsx", 10001), "export_too_many_rows") == {
        "count": "10,001"
    }
    assert helper_refused(owner_conn, expression, ("pdf", 1234567), "export_too_many_rows") == {
        "count": "1,234,567"
    }


def test_check_query_skips_the_page_only_when_both_are_null(owner_conn: Conn) -> None:
    expression = "reports.check_query(%s::text, %s::integer, %s::integer)"
    assert helper(owner_conn, expression, "  kda  ", None, None) == "kda"
    assert helper(owner_conn, expression, "   ", 1, 50) is None
    assert helper(owner_conn, expression, None, 1, 100) is None
    helper_refused(owner_conn, expression, (None, 0, 50), "page_out_of_range")
    helper_refused(owner_conn, expression, (None, 1, 101), "page_out_of_range")
    helper_refused(owner_conn, expression, (None, 1, None), "page_out_of_range")
    helper_refused(owner_conn, expression, ("x" * 201, 1, 50), "report_search_length")
    assert helper(owner_conn, expression, "x" * 200, 1, 50) == "x" * 200


# --- the exports ---


def test_an_export_writes_one_change_log_row_with_its_count(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    document = export(app_conn, fleet.owner, "fleet", "net", q=" kd ", now=at(10))
    assert [r[0] for r in document["rows"]] == ["KDC 200B", "KDA 482M", "KDB 111A"]
    assert document["total"] == 3
    assert nums(document["totals"])[2] == Decimal(26700)
    assert "page_number" not in document
    assert document["period"] == "1 Oct 2026 to 9 Oct 2026"
    assert document["filters"] == "All companies"
    assert document["exported_by"] == "Antony Maina"
    assert document["exported_on"] is not None
    assert isinstance(document["organization"], str) and document["organization"]
    assert isinstance(document["currency"], str) and document["currency"]
    assert document["file_name"] == "Net by vehicle 1 Oct 2026 to 9 Oct 2026.xlsx"
    assert document["content_type"] == XLSX
    assert set(document) >= {
        "group",
        "report",
        "title",
        "from_date",
        "to_date",
        "business_date",
        "headline",
        "figures",
        "columns",
        "rows",
        "total",
        "totals",
        "organization",
        "period",
        "filters",
        "exported_by",
        "exported_on",
        "currency",
        "file_name",
        "content_type",
    }

    [row] = change_rows(owner_conn, fleet.org, "reports")
    assert row["before"] == "null"
    assert row["vehicle_id"] is None
    assert row["actor_id"] == fleet.owner.id
    assert json.loads(row["after"]) == {
        "group": "fleet",
        "report": "net",
        "from": "2026-10-01",
        "to": "2026-10-09",
        "holderId": None,
        "companyId": None,
        "q": "kd",
        "rows": 3,
        "format": "xlsx",
    }
    assert row["reason"] == (
        'Exported Net by vehicle for 1 Oct 2026 to 9 Oct 2026, searched for "kd" to Excel'
    )
    [event] = audit_events(owner_conn, fleet.org, "reports.exported")
    assert event["after"]["rows"] == 3
    assert event["entity"]

    north = export(
        app_conn, fleet.owner, "fleet", "net", company=fleet.north, fmt=" PDF ", now=at(11)
    )
    assert north["filters"] == "North Star"
    assert north["content_type"] == "application/pdf"
    assert north["file_name"] == "Net by vehicle 1 Oct 2026 to 9 Oct 2026.pdf"
    assert [r[0] for r in north["rows"]] == ["KDA 482M", "KDB 111A"]
    rows = change_rows(owner_conn, fleet.org, "reports")
    assert len(rows) == 2
    assert rows[1]["reason"] == "Exported Net by vehicle for 1 Oct 2026 to 9 Oct 2026 to PDF"
    assert json.loads(rows[1]["after"])["companyId"] == str(fleet.north)
    assert json.loads(rows[1]["after"])["rows"] == 2

    undated = export(app_conn, fleet.owner, "fleet", "investment", None, None, now=at(12))
    assert undated["period"] is None
    assert undated["file_name"] == "Investment.xlsx"
    assert change_rows(owner_conn, fleet.org, "reports")[2]["reason"] == (
        "Exported Investment to Excel"
    )
    book = export(app_conn, fleet.admin, "pettycash", "cashBook", holder=fleet.clerk.id, now=at(13))
    assert book["filters"] == "Wanjiru Kamau"
    assert json.loads(change_rows(owner_conn, fleet.org, "reports")[3]["after"])["holderId"] == str(
        fleet.clerk.id
    )
    every = export(app_conn, fleet.admin, "pettycash", "managers", now=at(14))
    assert every["filters"] == "All floats"


def test_a_scoped_viewers_export_holds_no_hidden_vehicle(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    set_override(owner_conn, fleet.clerk, "reports.export")
    document = export(app_conn, fleet.clerk, "fleet", "net", now=at(10))
    assert [r[0] for r in document["rows"]] == ["KDA 482M", "KDB 111A"]
    assert document["exported_by"] == "Wanjiru Kamau"
    assert num(document["headline"]["value"]) == Decimal(9400)
    gaps = export(app_conn, fleet.clerk, "fleet", "gaps", now=at(11))
    assert len(gaps["rows"]) == 8
    assert json.loads(change_rows(owner_conn, fleet.org, "reports")[1]["after"])["rows"] == 8
    south = export(app_conn, fleet.clerk, "fleet", "net", company=fleet.south, now=at(12))
    assert south["rows"] == []
    assert south["filters"] == "All companies"


def test_the_screen_exports_list_what_their_screens_list(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    week = read(
        app_conn, "revenue_week_get", fleet.owner, oct(5), None, None, None, None, None, now=at(20)
    )
    revenue = read(app_conn, "revenue_export_get", fleet.owner, oct(5), None, None, now=at(20))
    assert (revenue["group"], revenue["report"], revenue["title"]) == ("revenue", "week", "Revenue")
    assert (revenue["from_date"], revenue["to_date"]) == ("2026-10-05", "2026-10-09")
    assert keys(revenue) == [
        "vehicle",
        "company",
        "2026-10-05",
        "2026-10-06",
        "2026-10-07",
        "2026-10-08",
        "2026-10-09",
        "2026-10-10",
        "2026-10-11",
        "total",
        "target",
        "gap",
    ]
    assert [c["label"] for c in revenue["columns"]][2:4] == ["Mon 5", "Tue 6"]
    assert [c["label"] for c in revenue["columns"]][-2] == "Target to date"
    expected = []
    for vehicle in week["vehicles"]:
        cells: list[Any] = [vehicle["registration"], vehicle["company_name"]]
        for day in vehicle["days"]:
            status = day["status"]
            cells.append(
                day["amount"]
                if status == "amount"
                else day["reason"]
                if status == "reason"
                else "Missing"
                if status == "missing"
                else None
            )
        cells += [vehicle["total_amount"], vehicle["total_expected"], vehicle["gap"]]
        expected.append(cells)
    assert revenue["rows"] == expected
    assert len(revenue["rows"]) == 3
    kdc = row_of(revenue, "KDC 200B")
    assert nums(kdc[2:6]) == [Decimal(2000), Decimal(2000), Decimal(2000), "Missing"]
    assert num(kdc[9]) == Decimal(6000)
    assert num(revenue["headline"]["value"]) == num(week["total_amount"])
    first_label, second_label = (f["label"] for f in revenue["figures"][:2])
    assert first_label == "Gap to target so far"
    assert second_label.startswith("Below ")
    assert figure(revenue, "Missing days") == num(week["missing_days"])
    assert revenue["file_name"] == "Revenue 5 Oct 2026 to 9 Oct 2026.xlsx"
    [logged] = change_rows(owner_conn, fleet.org, "reports")
    assert json.loads(logged["after"]) == {
        "screen": "revenue",
        "weekStart": "2026-10-05",
        "companyId": None,
        "rows": 3,
        "format": "xlsx",
    }
    assert logged["reason"] == "Exported Revenue for 5 Oct 2026 to 9 Oct 2026 to Excel"
    north = read(
        app_conn, "revenue_export_get", fleet.owner, oct(5), fleet.north, "pdf", now=at(21)
    )
    assert [r[0] for r in north["rows"]] == ["KDA 482M", "KDB 111A"]
    assert north["filters"] == "North Star"

    listed = read(
        app_conn,
        "pettycash_entry_list",
        fleet.owner,
        FIRST,
        TODAY,
        None,
        ["expense"],
        None,
        None,
        1,
        100,
    )
    petty = read(
        app_conn,
        "pettycash_export_get",
        fleet.owner,
        FIRST,
        TODAY,
        None,
        "expenses",
        None,
        None,
        None,
        now=at(22),
    )
    assert (petty["group"], petty["report"], petty["title"]) == (
        "pettycash",
        "expenses",
        "Petty cash, expenses",
    )
    assert keys(petty) == [
        "date",
        "manager",
        "vehicle",
        "item",
        "units",
        "unitAmount",
        "amount",
        "status",
        "note",
        "recordedBy",
    ]
    assert [nums(r) for r in petty["rows"]] == [
        [
            "2026-10-02",
            "Wanjiru Kamau",
            "KDA 482M",
            "Tyres",
            Decimal(2),
            Decimal(1500),
            Decimal(3000),
            "Approved",
            None,
            "Wanjiru Kamau",
        ],
        [
            "2026-10-03",
            "Wanjiru Kamau",
            "KDA 482M",
            "Diesel",
            Decimal(1),
            Decimal(3000),
            Decimal(3000),
            "Waiting",
            None,
            "Wanjiru Kamau",
        ],
    ]
    assert len(petty["rows"]) == listed["total"] == len(listed["items"])
    assert sorted(r[0] for r in petty["rows"]) == sorted(i["entry_date"] for i in listed["items"])
    assert (petty["headline"]["label"], num(petty["headline"]["value"])) == (
        "Cash balance",
        Decimal(3500),
    )
    assert figure(petty, "Cash received") == Decimal(10000)
    assert figure(petty, "Expenses") == Decimal(6000)
    assert figure(petty, "Credit notes") == Decimal(500)
    assert figure(petty, "Waiting") == Decimal(3000)
    assert petty["filters"] == "All floats"
    waiting = read(
        app_conn,
        "pettycash_export_get",
        fleet.owner,
        FIRST,
        TODAY,
        fleet.clerk.id,
        "expenses",
        ["waiting"],
        "diesel",
        "pdf",
        now=at(23),
    )
    assert [r[3] for r in waiting["rows"]] == ["Diesel"]
    assert waiting["filters"] == "Wanjiru Kamau, waiting"
    assert waiting["content_type"] == "application/pdf"
    cash = read(
        app_conn,
        "pettycash_export_get",
        fleet.owner,
        FIRST,
        TODAY,
        None,
        "cash",
        None,
        None,
        None,
        now=at(24),
    )
    assert cash["title"] == "Petty cash, cash received"
    assert keys(cash) == ["date", "manager", "description", "amount", "note", "recordedBy"]
    assert [nums(r) for r in cash["rows"]] == [
        ["2026-10-01", "Wanjiru Kamau", "Cash given", Decimal(10000), None, "Antony Maina"],
        ["2026-10-04", "Wanjiru Kamau", "Credit note", Decimal(-500), "Paid back", "Antony Maina"],
    ]
    refuses(
        app_conn,
        "pettycash_export_get",
        fleet.owner,
        [FIRST, TODAY, None, "all", None, None, None],
        "XC422",
        "pettycash_export_view_invalid",
    )
    refuses(
        app_conn,
        "pettycash_export_get",
        fleet.owner,
        [FIRST, TODAY, None, "expenses", ["open"], None, None],
        "XC422",
        "pettycash_status_invalid",
    )
    refuses(
        app_conn,
        "pettycash_export_get",
        fleet.owner,
        [FIRST, TODAY, uuid4(), "expenses", None, None, None],
        "XC404",
        "not_found",
    )
    refuses(
        app_conn,
        "pettycash_export_get",
        fleet.owner,
        [FIRST, None, None, "expenses", None, None, None],
        "XC422",
        "pettycash_range_both",
    )
    rows = change_rows(owner_conn, fleet.org, "reports")
    assert json.loads(rows[2]["after"]) == {
        "screen": "pettycash",
        "from": "2026-10-01",
        "to": "2026-10-09",
        "holderId": None,
        "view": "expenses",
        "status": None,
        "q": None,
        "rows": 2,
        "format": "xlsx",
    }
    assert json.loads(rows[3]["after"])["status"] == ["waiting"]
    assert rows[3]["reason"] == (
        'Exported Petty cash, expenses for 1 Oct 2026 to 9 Oct 2026, searched for "diesel" to PDF'
    )

    ledger = read(app_conn, "expenses_ledger_get", fleet.admin, FIRST, TODAY, None, None, 1, 100)
    expenses = read(
        app_conn, "expenses_export_get", fleet.admin, FIRST, TODAY, None, None, None, now=at(25)
    )
    assert (expenses["group"], expenses["report"], expenses["title"]) == (
        "expenses",
        "ledger",
        "Central expenses",
    )
    assert keys(expenses) == [
        "date",
        "vehicle",
        "item",
        "category",
        "quantity",
        "unitAmount",
        "amount",
        "source",
        "recordedBy",
    ]
    assert [r[0] for r in expenses["rows"]] == [i["entry_date"] for i in ledger["items"]]
    assert [num(r[6]) for r in expenses["rows"]] == [num(i["total"]) for i in ledger["items"]]
    assert len(expenses["rows"]) == 3
    assert nums(row_at(expenses, "2026-10-06")) == [
        "2026-10-06",
        "KDC 200B",
        "Tyres",
        "Repairs",
        Decimal(4),
        Decimal(1200),
        Decimal(4800),
        "Central",
        "Peter Otieno",
    ]
    assert nums(row_at(expenses, "2026-10-05"))[6:] == [Decimal(300), "Scheduled", "Standing order"]
    assert nums(row_at(expenses, "2026-10-02"))[6:] == [
        Decimal(3000),
        "Petty cash",
        "Wanjiru Kamau, Wanjiru Kamau's float",
    ]
    assert num(expenses["headline"]["value"]) == num(ledger["figures"]["total"])
    assert figure(expenses, "Central") == num(ledger["figures"]["central"])
    assert figure(expenses, "Petty cash") == num(ledger["figures"]["petty_cash"])
    assert figure(expenses, "Scheduled") == num(ledger["figures"]["scheduled"])
    central = read(
        app_conn,
        "expenses_export_get",
        fleet.admin,
        FIRST,
        TODAY,
        "central",
        "tyres",
        "PDF",
        now=at(26),
    )
    assert [r[7] for r in central["rows"]] == ["Central"]
    assert json.loads(change_rows(owner_conn, fleet.org, "reports")[-1]["after"]) == {
        "screen": "expenses",
        "from": "2026-10-01",
        "to": "2026-10-09",
        "source": "central",
        "q": "tyres",
        "rows": 1,
        "format": "pdf",
    }
    refuses(
        app_conn,
        "expenses_export_get",
        fleet.admin,
        [FIRST, TODAY, "nowhere", None, "csv"],
        "XC422",
        "export_format_invalid",
    )
    refuses(
        app_conn,
        "expenses_export_get",
        fleet.admin,
        [FIRST, TODAY, "nowhere", None, None],
        "XC422",
        "expense_source_invalid",
    )


def row_at(table: dict[str, Any], day: str) -> list[Any]:
    [found] = [r for r in table["rows"] if r[0] == day]
    return list(found)
