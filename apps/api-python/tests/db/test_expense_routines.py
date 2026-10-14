"""The central-expense routines (``api.expenses_*`` and their ``expenses.*`` helpers), called as
``xcode_app``: the purchase checks and their order, the split into one row per vehicle without a
cent lost or invented, the retried and racing record, the change and remove steps in order, the
group detachment, who may change what, the version conflict with ``current``, the back-dating
limit on record, change and remove, the change-log reasons and snapshots, and the ledger: three
sources, order, figures, search, paging and scope; the options.

The business date is 9 Oct 2026 (a Friday). Antony Maina owns the organization (every right),
Peter Otieno is an Office admin (record and edit expenses, every company) and Wanjiru Kamau a
Fleet manager who may record expenses (North Fleet only). Rules are the ``CE-*`` rows of
``docs/inventory/inventory-expenses-reports.md`` as ``docs/05-routines.md`` 11.2 builds them."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn
from ..support.setup_rows import (
    Version,
    add_away,
    add_category,
    add_item,
    add_main_category,
    add_schedule,
    change_rows,
    read,
    refuses,
)
from ..support.tenancy import (
    REQUEST,
    Member,
    add_company,
    add_vehicle,
    audit_events,
    provision_member,
    set_override,
    set_scope,
)

TODAY = date(2026, 10, 9)
NONE = UUID(int=0)


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


MONTH_AGO = day(-30)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def num(value: Any) -> Decimal:
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class Depot:
    owner: Member
    admin: Member
    clerk: Member
    north: UUID
    south: UUID
    kda: UUID
    kdb: UUID
    kdc: UUID
    running: UUID
    repairs: UUID
    tyres: UUID
    fuel: UUID

    @property
    def org(self) -> UUID:
        return self.owner.org


@pytest.fixture
def depot(operator_conn: Conn, owner_conn: Conn) -> Depot:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    admin = provision_member(operator_conn, 2, "Office admin", "Peter", "Otieno")
    clerk = provision_member(operator_conn, 3, "Fleet manager", "Wanjiru", "Kamau")
    org = owner.org
    north = add_company(owner_conn, org, "North Fleet")
    south = add_company(owner_conn, org, "South Fleet")
    kda = add_vehicle(owner_conn, org, north, "KDA 103A", joined_on=day(-60), fleet_number="N-01")
    kdb = add_vehicle(owner_conn, org, north, "KDB 204B", joined_on=day(-60))
    kdc = add_vehicle(owner_conn, org, south, "KDC 305C", joined_on=day(-60))
    set_scope(owner_conn, owner, org, all_companies=True)
    set_scope(owner_conn, admin, org, all_companies=True)
    set_scope(owner_conn, clerk, org, companies=[north])
    set_override(owner_conn, clerk, "expenses.capture")
    running = add_main_category(owner_conn, org, "Running")
    repairs = add_category(owner_conn, org, "Repairs", bucket=1, main_category=running)
    tyres = add_item(owner_conn, org, repairs, "Tyres")
    fuelling = add_category(owner_conn, org, "Fuelling", bucket=None)
    fuel = add_item(owner_conn, org, fuelling, "Diesel")
    return Depot(owner, admin, clerk, north, south, kda, kdb, kdc, running, repairs, tyres, fuel)


def allocations(*pairs: tuple[UUID, Any]) -> Jsonb:
    return Jsonb([{"vehicle_id": str(v), "amount": str(a)} for v, a in pairs])


def purchase_args(
    depot: Depot,
    units: Any,
    unit_amount: Any,
    pairs: list[tuple[UUID, Any]],
    *,
    on: date | None = TODAY,
    item: UUID | None = None,
    note: str | None = None,
    purchase: UUID | None = None,
) -> list[Any]:
    return [
        purchase,
        on,
        item or depot.tyres,
        None if units is None else num(units),
        None if unit_amount is None else num(unit_amount),
        note,
        allocations(*pairs),
    ]


def record(
    app: Conn,
    depot: Depot,
    units: Any,
    unit_amount: Any,
    pairs: list[tuple[UUID, Any]],
    *,
    who: Member | None = None,
    now: datetime = T0,
    **fields: Any,
) -> Any:
    args = purchase_args(depot, units, unit_amount, pairs, **fields)
    return read(app, "expenses_entry_create", who or depot.admin, *args, now=now)


def record_refused(
    app: Conn,
    depot: Depot,
    args: list[Any],
    sqlstate: str,
    code: str,
    *,
    who: Member | None = None,
) -> psycopg.Error:
    return refuses(app, "expenses_entry_create", who or depot.admin, args, sqlstate, code)


def one(app: Conn, depot: Depot, amount: Any = 4000, **fields: Any) -> UUID:
    """One central expense of one unit on KDA 103A; its id."""
    vehicle = fields.pop("vehicle", depot.kda)
    made = record(app, depot, 1, amount, [(vehicle, amount)], **fields)
    return UUID(made["ids"][0])


def change_args(
    row_id: UUID,
    *,
    on: date | None,
    vehicle: UUID | None,
    item: UUID | None,
    units: Any,
    unit_amount: Any,
    note: str | None = None,
    version: int | None = 1,
) -> list[Any]:
    return [
        row_id,
        on,
        vehicle,
        item,
        None if units is None else num(units),
        None if unit_amount is None else num(unit_amount),
        note,
        version,
    ]


def change(app: Conn, who: Member, args: list[Any], *, now: datetime = T0) -> Any:
    return read(app, "expenses_entry_update", who, *args, now=now)


def remove(
    app: Conn, who: Member, row_id: UUID, version: int | None, reason: str | None, **kw: Any
) -> Any:
    return read(app, "expenses_entry_remove", who, row_id, version, reason, **kw)


def ledger(
    app: Conn,
    who: Member,
    start: date | None = MONTH_AGO,
    end: date | None = TODAY,
    *,
    source: str | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 100,
) -> Any:
    return read(app, "expenses_ledger_get", who, start, end, source, q, page, size)


def stored(owner_conn: Conn, row_id: UUID) -> dict[str, Any]:
    row = owner_conn.execute("SELECT * FROM expenses.entries WHERE id = %s", (row_id,)).fetchone()
    assert row is not None
    return row


def purchase_rows(owner_conn: Conn, group: UUID) -> list[dict[str, Any]]:
    return owner_conn.execute(
        "SELECT * FROM expenses.entries WHERE group_id = %s ORDER BY id", (group,)
    ).fetchall()


def detail(error: psycopg.Error) -> dict[str, Any]:
    text = error.diag.message_detail
    return json.loads(text) if text else {}


def reasons(owner_conn: Conn, depot: Depot) -> list[str]:
    return [str(r["reason"]) for r in change_rows(owner_conn, depot.org, "centralexpenses")]


def set_back_limit(owner_conn: Conn, member: Member, days: int) -> None:
    owner_conn.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = 'days', back_limit_count = %s "
        "WHERE organization_id = %s AND user_id = %s",
        (days, member.org, member.id),
    )


def insert_row(
    owner_conn: Conn,
    depot: Depot,
    vehicle: UUID,
    on: date,
    amount: Any,
    *,
    by: Member | None = None,
    item: UUID | None = None,
    note: str | None = None,
) -> UUID:
    """A central expense written as the owner: dates and recorders no routine would accept."""
    recorder = (by or depot.admin).id
    row = owner_conn.execute(
        "WITH n AS (SELECT gen_random_uuid() AS id) INSERT INTO expenses.entries (organization_id, "
        "id, entry_date, vehicle_id, expense_item_id, units, unit_amount, note, group_id, "
        "group_size, group_total, group_units, group_unit_amount, recorded_by, recorded_at, "
        "updated_by, updated_at) SELECT %s, n.id, %s, %s, %s, 1, %s, %s, n.id, 1, %s, 1, %s, %s, "
        "%s, %s, %s FROM n RETURNING id",
        (
            depot.org,
            on,
            vehicle,
            item or depot.tyres,
            num(amount),
            note,
            num(amount),
            num(amount),
            recorder,
            T0,
            recorder,
            T0,
        ),
    ).fetchone()
    assert row is not None
    return UUID(str(row["id"]))


def petty_expense(
    owner_conn: Conn,
    depot: Depot,
    vehicle: UUID,
    on: date,
    amount: Any,
    *,
    status: int = 2,
    note: str | None = None,
) -> UUID:
    reviewed = depot.owner.id if status == 2 else None
    row = owner_conn.execute(
        "INSERT INTO pettycash.entries (organization_id, holder_id, kind, entry_date, vehicle_id, "
        "expense_item_id, unit_amount, note, status, reviewed_by, reviewed_at, recorded_by, "
        "recorded_at, updated_by, updated_at) VALUES (%s, %s, 2, %s, %s, %s, %s, %s, %s, %s, %s, "
        "%s, %s, %s, %s) RETURNING id",
        (
            depot.org,
            depot.clerk.id,
            on,
            vehicle,
            depot.fuel,
            num(amount),
            note,
            status,
            reviewed,
            T0 if reviewed else None,
            depot.clerk.id,
            T0,
            depot.clerk.id,
            T0,
        ),
    ).fetchone()
    assert row is not None
    return UUID(str(row["id"]))


def blocked_on(owner_conn: Conn, waiting: int, holder: int) -> bool:
    for _ in range(200):
        row = owner_conn.execute("SELECT pg_blocking_pids(%s) AS pids", (waiting,)).fetchone()
        if row is not None and holder in row["pids"]:
            return True
        threading.Event().wait(0.05)
    return False


# --- record a purchase ---


def test_one_vehicle_takes_the_purchase_as_typed_and_its_id(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    purchase = uuid4()
    made = record(
        app_conn, depot, 2, 2000, [(depot.kda, 4000)], purchase=purchase, note="  Two tyres "
    )
    assert made == {"ids": [str(purchase)], "total": 4000}
    row = stored(owner_conn, purchase)
    assert (
        row["group_id"],
        row["group_size"],
        row["group_total"],
        row["group_units"],
        row["group_unit_amount"],
    ) == (purchase, 1, 4000, 2, 2000)
    assert (row["units"], row["unit_amount"], row["total"], row["note"], row["version"]) == (
        2,
        2000,
        4000,
        "Two tyres",
        1,
    )
    [logged] = change_rows(owner_conn, depot.org, "centralexpenses")
    assert (logged["entity_id"], logged["vehicle_id"], logged["before"]) == (
        purchase,
        depot.kda,
        "null",
    )
    assert (
        logged["reason"] == "Recorded central expense on KDA 103A for 9 Oct 2026: Tyres, KES 4,000"
    )
    [audit] = audit_events(owner_conn, depot.org, "expenses.recorded")
    assert (audit["entity"], audit["before"], audit["after"]["Total"]) == (
        str(purchase),
        None,
        4000,
    )


def test_the_snapshot_keeps_the_dotnet_keys_in_their_order(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    row_id = one(app_conn, depot, "1500.50", note="Front pair")
    [logged] = change_rows(owner_conn, depot.org, "centralexpenses")
    after = json.loads(str(logged["after"]))
    assert list(after) == [
        "Id",
        "Date",
        "VehicleId",
        "ExpenseItemId",
        "Units",
        "UnitAmount",
        "Total",
        "Note",
        "GroupId",
        "GroupSize",
        "GroupTotal",
        "GroupUnits",
        "GroupUnitAmount",
        "RecordedBy",
        "RecordedAt",
        "UpdatedBy",
        "UpdatedAt",
        "RemovedBy",
        "RemovedAt",
        "RemovalReason",
        "Version",
    ]
    assert (after["Id"], after["Date"], after["Total"], after["Units"]) == (
        str(row_id),
        "2026-10-09",
        1500.5,
        1,
    )
    assert (after["RecordedAt"], after["RemovedAt"], after["Version"]) == (
        "2026-10-09T07:00:00.000000+00:00",
        None,
        1,
    )
    assert logged["reason"].endswith("Tyres, KES 1,500.50")


@pytest.mark.parametrize(
    ("units", "unit_amount", "amounts", "rows"),
    [
        ("1", "100", ["33.34", "33.33", "33.33"], [("1", "33.34"), ("1", "33.33"), ("1", "33.33")]),
        ("10", "4", ["10", "10", "10", "10"], [("2.5", "4")] * 4),
        ("3", "10", ["10", "10", "10"], [("1", "10")] * 3),
        ("1", "-90", ["-30", "-30", "-30"], [("1", "-30")] * 3),
        ("6", "-15", ["-30", "-30", "-30"], [("2", "-15")] * 3),
        ("2", "1500", ["2000", "1000"], [("1", "2000"), ("1", "1000")]),
        ("1", "0.10", ["0.05", "0.05"], [("0.5", "0.10")] * 2),
        ("1", "0.15", ["0.08", "0.07"], [("1", "0.08"), ("1", "0.07")]),
        ("3", "33.33", ["49.99", "50"], [("1", "49.99"), ("1", "50")]),
    ],
)
def test_a_split_never_loses_or_invents_a_cent(
    app_conn: Conn,
    owner_conn: Conn,
    depot: Depot,
    units: str,
    unit_amount: str,
    amounts: list[str],
    rows: list[tuple[str, str]],
) -> None:
    """Equal amounts keep the unit cost while the share of units has three decimals and costs
    the amount exactly; anything else is one unit at the vehicle's amount. The rows add up to
    the purchase, which every row keeps as bought."""
    vehicles = [depot.kda, depot.kdb, depot.kdc, uuid4()][: len(amounts)]
    if len(amounts) == 4:
        vehicles[3] = add_vehicle(owner_conn, depot.org, depot.north, "KDD 406D", joined_on=day(-9))
    purchase = uuid4()
    made = record(
        app_conn,
        depot,
        units,
        unit_amount,
        list(zip(vehicles, amounts, strict=True)),
        purchase=purchase,
    )
    total = (num(units) * num(unit_amount)).quantize(Decimal("0.01"))
    assert num(made["total"]) == total
    stored_rows = {r["id"]: r for r in purchase_rows(owner_conn, purchase)}
    ordered = [stored_rows[UUID(i)] for i in made["ids"]]
    assert [r["vehicle_id"] for r in ordered] == vehicles
    assert [(r["units"], r["unit_amount"]) for r in ordered] == [(num(u), num(a)) for u, a in rows]
    assert [r["total"] for r in ordered] == [num(a) for a in amounts]
    assert sum(r["total"] for r in ordered) == total
    for r in ordered:
        assert (r["group_size"], r["group_total"], r["group_units"], r["group_unit_amount"]) == (
            len(amounts),
            total,
            num(units),
            num(unit_amount),
        )
        assert r["id"] != purchase


def test_fifty_vehicles_share_one_purchase_and_fifty_one_are_refused(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    fleet = [
        add_vehicle(owner_conn, depot.org, depot.north, f"KEA {n:03d}A", joined_on=day(-9))
        for n in range(51)
    ]
    made = record(app_conn, depot, 1, 100, [(v, "2.00") for v in fleet[:50]])
    rows = owner_conn.execute(
        "SELECT units, unit_amount, total, group_size FROM expenses.entries WHERE id = ANY (%s)",
        ([UUID(i) for i in made["ids"]],),
    ).fetchall()
    assert len(rows) == 50
    assert {(r["units"], r["unit_amount"], r["total"], r["group_size"]) for r in rows} == {
        (Decimal("0.020"), Decimal("100.00"), Decimal("2.00"), 50)
    }
    args = purchase_args(depot, 1, "102", [(v, "2.00") for v in fleet])
    record_refused(app_conn, depot, args, "XC422", "expense_vehicles_invalid")


_LONG = "x" * 81


@pytest.mark.parametrize(
    ("units", "unit_amount", "on", "item", "note", "pairs", "code"),
    [
        (0, 0, None, None, _LONG, "none", "expense_vehicles_invalid"),
        (0, 0, None, None, _LONG, "empty", "expense_vehicles_invalid"),
        (0, 0, None, None, _LONG, "repeated", "expense_vehicles_invalid"),
        (0, 0, None, None, _LONG, "blank vehicle", "expense_vehicles_invalid"),
        (0, 0, None, None, _LONG, "not a vehicle", "expense_vehicles_invalid"),
        (0, 0, None, None, _LONG, "zero", "pettycash_line_date_required"),
        (0, 0, TODAY, None, _LONG, "zero", "pettycash_line_amount_zero"),
        (0, "10.005", TODAY, None, _LONG, "zero", "pettycash_line_amount_decimals"),
        (0, 10, TODAY, None, _LONG, "zero", "pettycash_line_units"),
        ("1.2345", 10, TODAY, None, _LONG, "zero", "pettycash_line_units"),
        ("0.001", "0.01", TODAY, None, _LONG, "zero", "pettycash_line_total_zero"),
        ("999999999.999", 10000, TODAY, None, _LONG, "zero", "pettycash_line_total_large"),
        (1, 10, TODAY, None, _LONG, "zero", "pettycash_line_note_length"),
        (1, 10, TODAY, None, None, "zero", "pettycash_line_item_required"),
        (1, 10, TODAY, "tyres", None, "zero", "expense_allocation_amount"),
        (1, 10, TODAY, "tyres", None, "three decimals", "expense_allocation_amount"),
        (1, 10, TODAY, "tyres", None, "a word", "expense_allocation_amount"),
        (1, 10, TODAY, "tyres", None, "opposite sign", "expense_allocation_sign"),
        (1, 10, TODAY, "tyres", None, "short", "expense_allocation_sum"),
    ],
)
def test_the_purchase_checks_run_in_their_order(
    app_conn: Conn,
    depot: Depot,
    units: Any,
    unit_amount: Any,
    on: date | None,
    item: str | None,
    note: str | None,
    pairs: str,
    code: str,
) -> None:
    """The vehicles first, then the line as a petty-cash expense line, then each vehicle's
    amount, its sign and their sum; every case also fails the checks after its own."""
    kda, kdb = str(depot.kda), str(depot.kdb)
    shaped: dict[str, Any] = {
        "none": None,
        "empty": [],
        "repeated": [{"vehicle_id": kda, "amount": "0"}, {"vehicle_id": kda, "amount": "0"}],
        "blank vehicle": [{"vehicle_id": str(NONE), "amount": "0"}],
        "not a vehicle": [{"vehicle_id": "KDA 103A", "amount": "0"}],
        "zero": [{"vehicle_id": kda, "amount": "0"}, {"vehicle_id": kdb, "amount": "-5"}],
        "three decimals": [
            {"vehicle_id": kda, "amount": "5.005"},
            {"vehicle_id": kdb, "amount": "-1"},
        ],
        "a word": [{"vehicle_id": kda, "amount": "five"}, {"vehicle_id": kdb, "amount": "-1"}],
        "opposite sign": [{"vehicle_id": kda, "amount": "15"}, {"vehicle_id": kdb, "amount": "-1"}],
        "short": [{"vehicle_id": kda, "amount": "5"}, {"vehicle_id": kdb, "amount": "4.99"}],
    }
    value = shaped[pairs]
    args = [
        None,
        on,
        depot.tyres if item == "tyres" else None,
        num(units),
        num(unit_amount),
        note,
        None if value is None else Jsonb(value),
    ]
    record_refused(app_conn, depot, args, "XC422", code)


def test_a_purchase_amount_sent_as_a_json_number_is_read_exactly(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    exact = Jsonb(
        [
            {"vehicle_id": str(depot.kda), "amount": Decimal("12.5")},
            {"vehicle_id": str(depot.kdb), "amount": Decimal("7.5")},
        ],
        dumps=lambda value: (
            json.dumps(value, default=str).replace('"12.5"', "12.5").replace('"7.5"', "7.5")
        ),
    )
    made = read(
        app_conn,
        "expenses_entry_create",
        depot.admin,
        None,
        TODAY,
        depot.tyres,
        num(1),
        num(20),
        None,
        exact,
    )
    assert num(made["total"]) == 20
    third = Jsonb(
        [{"vehicle_id": str(depot.kda), "amount": 0}],
        dumps=lambda value: json.dumps(value).replace(": 0}", ": 20.001}"),
    )
    record_refused(
        app_conn,
        depot,
        [None, TODAY, depot.tyres, num(1), num(20), None, third],
        "XC422",
        "expense_allocation_amount",
    )


def test_the_record_steps_answer_in_their_order(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, depot: Depot
) -> None:
    viewer = provision_member(operator_conn, 4, "Fleet manager", "Grace", "Wambui")
    set_scope(owner_conn, viewer, depot.org, all_companies=True)
    good = purchase_args(depot, 1, 500, [(depot.kda, 500)])
    record_refused(app_conn, depot, good, "XC403", "permission_missing", who=viewer)

    kept = uuid4()
    record(app_conn, depot, 1, 500, [(depot.kda, 500)], purchase=kept)
    retried = purchase_args(depot, 1, 500, [(depot.kdc, 500)], on=day(5), purchase=kept)
    assert read(app_conn, "expenses_entry_create", depot.admin, *retried) == {
        "ids": [str(kept)],
        "total": 500,
    }

    future = purchase_args(depot, 1, 500, [(uuid4(), 500)], on=day(1), item=uuid4())
    record_refused(app_conn, depot, future, "XC422", "expense_date_future")
    old = purchase_args(depot, 1, 500, [(uuid4(), 500)], on=day(-3651), item=uuid4())
    record_refused(app_conn, depot, old, "XC422", "expense_date_too_old")
    veteran = add_vehicle(owner_conn, depot.org, depot.north, "KAZ 001A", joined_on=day(-4000))
    record(app_conn, depot, 1, 500, [(veteran, 500)], on=day(-3650))

    set_back_limit(owner_conn, depot.admin, 2)
    limited = purchase_args(depot, 1, 500, [(uuid4(), 500)], on=day(-3), item=uuid4())
    record_refused(app_conn, depot, limited, "XC422", "record_too_old")
    owner_conn.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = 'none', back_limit_count = NULL "
        "WHERE organization_id = %s AND user_id = %s",
        (depot.org, depot.admin.id),
    )

    unknown = purchase_args(depot, 1, 500, [(depot.kda, 250), (uuid4(), 250)], item=uuid4())
    record_refused(app_conn, depot, unknown, "XC422", "expense_vehicle_not_yours")
    hidden = purchase_args(depot, 1, 500, [(depot.kdc, 500)], item=uuid4())
    record_refused(app_conn, depot, hidden, "XC422", "expense_vehicle_not_yours", who=depot.clerk)

    add_away(owner_conn, depot.org, depot.kdb, day(-2), day(3))
    away = purchase_args(depot, 1, 500, [(depot.kda, 250), (depot.kdb, 250)], item=uuid4())
    error = record_refused(app_conn, depot, away, "XC422", "expense_vehicle_inactive")
    assert detail(error) == {"registration": "KDB 204B"}
    early = purchase_args(depot, 1, 500, [(depot.kda, 500)], on=day(-61), item=uuid4())
    error = record_refused(app_conn, depot, early, "XC422", "expense_vehicle_inactive")
    assert detail(error) == {"registration": "KDA 103A"}

    record_refused(
        app_conn,
        depot,
        purchase_args(depot, 1, 500, [(depot.kda, 500)], item=uuid4()),
        "XC422",
        "expense_item_not_in_use",
    )
    stopped = add_item(owner_conn, depot.org, depot.repairs, "Rims", stopped_on=TODAY)
    record_refused(
        app_conn,
        depot,
        purchase_args(depot, 1, 500, [(depot.kda, 500)], item=stopped),
        "XC422",
        "expense_item_not_in_use",
    )
    closed = add_category(owner_conn, depot.org, "Fines", stopped_on=day(-1))
    fine = add_item(owner_conn, depot.org, closed, "Parking")
    record_refused(
        app_conn,
        depot,
        purchase_args(depot, 1, 500, [(depot.kda, 500)], item=fine),
        "XC422",
        "expense_item_not_in_use",
    )
    record(app_conn, depot, 1, 500, [(depot.kda, 500)], on=day(-2), item=fine)
    assert len(change_rows(owner_conn, depot.org, "centralexpenses")) == 3


def test_a_retried_record_answers_the_rows_it_made_whatever_the_body(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    """Rows found by the purchase id, removed or changed or not, ordered by id, with the first
    one's stored purchase total; nothing new is written or logged."""
    purchase = uuid4()
    made = record(
        app_conn,
        depot,
        3,
        100,
        [(depot.kda, 100), (depot.kdb, 100), (depot.kdc, 100)],
        purchase=purchase,
    )
    ids = sorted(made["ids"], key=UUID)
    again = record(app_conn, depot, 1, 999, [(depot.kda, 999)], purchase=purchase)
    assert again == {"ids": ids, "total": 300}
    first = UUID(ids[0])
    change(
        app_conn,
        depot.admin,
        change_args(
            first,
            on=TODAY,
            vehicle=stored(owner_conn, first)["vehicle_id"],
            item=depot.tyres,
            units=2,
            unit_amount=100,
        ),
    )
    remove(app_conn, depot.admin, UUID(ids[1]), 1, "Bought twice")
    later = record(app_conn, depot, 1, 999, [(depot.kda, 999)], purchase=purchase, on=day(4))
    assert later == {"ids": ids, "total": 200}
    assert len(change_rows(owner_conn, depot.org, "centralexpenses")) == 5


def test_a_purchase_id_another_purchase_or_person_holds_is_a_conflict(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    purchase = uuid4()
    made = record(app_conn, depot, 2, 100, [(depot.kda, 100), (depot.kdb, 100)], purchase=purchase)
    stolen = purchase_args(depot, 1, 100, [(depot.kda, 100)], purchase=purchase)
    error = record_refused(
        app_conn, depot, stolen, "XC409", "expense_saved_by_other", who=depot.clerk
    )
    assert detail(error) == {}
    part = purchase_args(depot, 1, 100, [(depot.kda, 100)], purchase=UUID(made["ids"][0]))
    record_refused(app_conn, depot, part, "XC409", "expense_saved_by_other")
    assert len(change_rows(owner_conn, depot.org, "centralexpenses")) == 2


def test_an_id_another_organization_uses_is_a_new_purchase_here(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    other = seed_organization(owner_conn)
    theirs = "SELECT * FROM expenses.entries WHERE organization_id = %s AND id = %s"
    before = owner_conn.execute(theirs, (other.org, other.central)).fetchone()
    made = record(app_conn, depot, 1, 300, [(depot.kda, 300)], purchase=other.central)
    assert made == {"ids": [str(other.central)], "total": 300}
    assert owner_conn.execute(theirs, (other.org, other.central)).fetchone() == before


def test_two_connections_recording_one_purchase_make_one_set_of_rows(
    app_url: str, owner_conn: Conn, depot: Depot
) -> None:
    """The second waits on the purchase's advisory lock, then finds the first one's rows and
    answers them as a retry: one set of rows, one log row each."""
    purchase = uuid4()
    args = purchase_args(depot, 2, 100, [(depot.kda, 100), (depot.kdb, 100)], purchase=purchase)
    sql = "SELECT api.expenses_entry_create(" + ", ".join(["%s"] * 11) + ") AS r"
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        outcome: list[Any] = []

        def late() -> None:
            try:
                outcome.append(
                    second.execute(
                        sql, (depot.admin.id, depot.org, REQUEST, *args, at(1))
                    ).fetchone()
                )
            except psycopg.Error as error:
                outcome.append(error)

        with first.transaction():
            made = first.execute(sql, (depot.admin.id, depot.org, REQUEST, *args, at(0))).fetchone()
            worker = threading.Thread(target=late)
            worker.start()
            assert blocked_on(owner_conn, second.info.backend_pid, first.info.backend_pid)
        worker.join(10)
    assert made is not None
    [answer] = outcome
    assert answer["r"] == {"ids": sorted(made["r"]["ids"], key=UUID), "total": 200}
    assert len(purchase_rows(owner_conn, purchase)) == 2
    assert len(change_rows(owner_conn, depot.org, "centralexpenses")) == 2


# --- change a row ---


def test_the_change_steps_answer_in_their_order(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    admins = one(app_conn, depot, 500)
    hidden = one(app_conn, depot, 500, vehicle=depot.kdc)
    gone = one(app_conn, depot, 500)
    remove(app_conn, depot.admin, gone, 1, "Wrong day")
    own_today = one(app_conn, depot, 500, who=depot.clerk)
    own_earlier = insert_row(owner_conn, depot, depot.kda, day(-1), 500, by=depot.clerk)

    def same(row_id: UUID, **overrides: Any) -> list[Any]:
        row = stored(owner_conn, row_id)
        fields = {
            "on": row["entry_date"],
            "vehicle": row["vehicle_id"],
            "item": row["expense_item_id"],
            "units": row["units"],
            "unit_amount": row["unit_amount"],
            "note": row["note"],
            "version": row["version"],
        }
        return change_args(row_id, **{**fields, **overrides})

    def refused(who: Member, args: list[Any], sqlstate: str, code: str) -> psycopg.Error:
        return refuses(app_conn, "expenses_entry_update", who, args, sqlstate, code)

    viewer = depot.owner
    set_override(owner_conn, viewer, "expenses.capture", False)
    set_override(owner_conn, viewer, "expenses.correct", False)
    refused(viewer, same(admins), "XC403", "permission_missing")
    unknown = uuid4()
    line = {"on": TODAY, "vehicle": depot.kda, "item": depot.tyres, "units": 1}
    refused(
        depot.admin,
        change_args(unknown, **line, unit_amount=0),
        "XC422",
        "pettycash_line_amount_zero",
    )
    refused(
        depot.admin,
        change_args(unknown, **{**line, "vehicle": None}, unit_amount=5),
        "XC422",
        "pettycash_line_vehicle_required",
    )
    refused(depot.admin, change_args(unknown, **line, unit_amount=5), "XC404", "not_found")
    refused(depot.clerk, same(hidden, unit_amount=600), "XC404", "not_found")
    refused(depot.admin, same(gone, unit_amount=600, version=2), "XC404", "not_found")

    assert change(app_conn, depot.clerk, same(admins, version=None)) == {
        "id": str(admins),
        "version": 1,
    }
    refused(depot.clerk, same(admins, unit_amount=600), "XC403", "expense_change_other")
    refused(depot.clerk, same(own_earlier, unit_amount=600), "XC403", "expense_change_earlier_day")
    refused(depot.clerk, same(own_today, on=day(-1)), "XC403", "expense_change_date")
    assert change(app_conn, depot.clerk, same(own_today, unit_amount=600)) == {
        "id": str(own_today),
        "version": 2,
    }

    old = insert_row(owner_conn, depot, depot.kda, day(-5), 500)
    set_back_limit(owner_conn, depot.admin, 2)
    refused(depot.admin, same(old, unit_amount=600, version=None), "XC422", "record_too_old")
    refused(
        depot.admin,
        same(admins, unit_amount=600, on=day(-3), version=None),
        "XC422",
        "expense_version_required",
    )
    error = refused(
        depot.admin,
        same(admins, unit_amount=600, on=day(-3), version=7),
        "XC409",
        "expense_version_conflict",
    )
    assert detail(error)["current"]["version"] == 1
    refused(depot.admin, same(admins, on=day(1), item=uuid4()), "XC422", "expense_date_future")
    refused(depot.admin, same(admins, on=day(-3), item=uuid4()), "XC422", "record_too_old")
    owner_conn.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = 'none', back_limit_count = NULL "
        "WHERE organization_id = %s AND user_id = %s",
        (depot.org, depot.admin.id),
    )
    refused(depot.admin, same(admins, on=day(-3651), item=uuid4()), "XC422", "expense_date_too_old")
    refused(
        depot.admin,
        same(admins, vehicle=uuid4(), item=uuid4()),
        "XC422",
        "expense_vehicle_not_yours",
    )
    add_away(owner_conn, depot.org, depot.kdb, day(-4), day(-2))
    error = refused(
        depot.admin,
        same(admins, vehicle=depot.kdb, on=day(-3), item=uuid4()),
        "XC422",
        "expense_vehicle_inactive",
    )
    assert detail(error) == {"registration": "KDB 204B"}
    refused(
        depot.admin,
        same(admins, on=day(-3), vehicle=depot.kdb),
        "XC422",
        "expense_vehicle_inactive",
    )
    refused(depot.admin, same(admins, item=uuid4()), "XC422", "expense_item_not_in_use")
    refused(depot.admin, same(admins, on=day(-1), item=uuid4()), "XC422", "expense_item_not_in_use")

    shared = record(app_conn, depot, 2, 100, [(depot.kda, 100), (depot.kdb, 100)])
    first, second = (UUID(i) for i in shared["ids"])
    error = refused(
        depot.admin, same(first, vehicle=depot.kdb), "XC422", "expense_purchase_has_vehicle"
    )
    assert detail(error) == {"registration": "KDB 204B"}
    remove(app_conn, depot.admin, second, 1, "Only one tyre")
    refused(depot.admin, same(first, vehicle=depot.kdb), "XC422", "expense_purchase_has_vehicle")
    moved = change(app_conn, depot.admin, same(first, vehicle=depot.kdc))
    assert moved == {"id": str(first), "version": 2}


def test_a_new_item_units_or_amount_leaves_the_group_and_a_new_date_vehicle_or_note_keeps_it(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    extra = add_vehicle(owner_conn, depot.org, depot.south, "KDE 507E", joined_on=day(-9))
    purchase = uuid4()
    made = record(
        app_conn,
        depot,
        3,
        100,
        [(depot.kda, 100), (depot.kdb, 100), (depot.kdc, 100)],
        purchase=purchase,
    )
    first, second, third = (UUID(i) for i in made["ids"])

    def args(row_id: UUID, version: int = 1, **overrides: Any) -> list[Any]:
        row = stored(owner_conn, row_id)
        fields = {
            "on": row["entry_date"],
            "vehicle": row["vehicle_id"],
            "item": row["expense_item_id"],
            "units": row["units"],
            "unit_amount": row["unit_amount"],
            "note": row["note"],
        }
        return change_args(row_id, version=version, **{**fields, **overrides})

    change(app_conn, depot.admin, args(first, note="Fitted"))
    change(app_conn, depot.admin, args(first, 2, on=day(-1)))
    change(app_conn, depot.admin, args(third, vehicle=extra))
    for kept in (first, third):
        row = stored(owner_conn, kept)
        assert (row["group_id"], row["group_size"], row["group_total"], row["group_units"]) == (
            purchase,
            3,
            300,
            3,
        )
    change(app_conn, depot.admin, args(second, units=2))
    row = stored(owner_conn, second)
    assert (
        row["group_id"],
        row["group_size"],
        row["group_total"],
        row["group_units"],
        row["group_unit_amount"],
        row["total"],
    ) == (purchase, 1, 200, 2, 100, 200)
    assert stored(owner_conn, first)["group_size"] == 3
    item_moved = args(first, 3, item=depot.fuel)
    change(app_conn, depot.admin, item_moved)
    assert stored(owner_conn, first)["group_size"] == 1
    priced = args(third, 2, unit_amount=120)
    change(app_conn, depot.admin, priced)
    assert (stored(owner_conn, third)["group_total"], stored(owner_conn, third)["version"]) == (
        120,
        3,
    )
    again = record(app_conn, depot, 1, 5, [(depot.kda, 5)], purchase=purchase)
    assert again["ids"] == sorted(made["ids"], key=UUID)


def test_a_change_is_logged_with_the_values_after_it(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    row_id = one(app_conn, depot, 4000)
    change(
        app_conn,
        depot.admin,
        change_args(
            row_id, on=day(-1), vehicle=depot.kdb, item=depot.fuel, units=3, unit_amount="500.17"
        ),
    )
    logged = change_rows(owner_conn, depot.org, "centralexpenses")[-1]
    assert logged["reason"] == (
        "Changed central expense on KDB 204B for 8 Oct 2026: Diesel, KES 1,500.51"
    )
    assert logged["vehicle_id"] == depot.kdb
    before, after = json.loads(str(logged["before"])), json.loads(str(logged["after"]))
    assert (before["VehicleId"], before["Version"], after["VehicleId"], after["Version"]) == (
        str(depot.kda),
        1,
        str(depot.kdb),
        2,
    )
    assert (after["UpdatedBy"], after["GroupSize"], after["GroupTotal"]) == (
        str(depot.admin.id),
        1,
        1500.51,
    )


def test_the_stale_writer_on_a_second_connection_gets_the_version_conflict_with_current(
    app_url: str, owner_conn: Conn, depot: Depot
) -> None:
    """The row lock serialises the two saves: the second waits, then reads the first one's
    version and answers 409 with the row as the ledger lists it now."""
    with psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as setup:
        made = read(
            setup,
            "expenses_entry_create",
            depot.admin,
            *purchase_args(depot, 1, 400, [(depot.kda, 400)]),
        )
    row_id = UUID(made["ids"][0])
    sql = "SELECT api.expenses_entry_update(" + ", ".join(["%s"] * 12) + ") AS r"
    first_args = change_args(
        row_id, on=TODAY, vehicle=depot.kda, item=depot.tyres, units=1, unit_amount=450
    )
    second_args = change_args(
        row_id, on=TODAY, vehicle=depot.kda, item=depot.tyres, units=1, unit_amount=480
    )
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        outcome: list[Any] = []

        def late() -> None:
            try:
                outcome.append(
                    second.execute(
                        sql, (depot.owner.id, depot.org, REQUEST, *second_args, at(1))
                    ).fetchone()
                )
            except psycopg.Error as error:
                outcome.append(error)

        with first.transaction():
            first.execute(sql, (depot.admin.id, depot.org, REQUEST, *first_args, at(0)))
            worker = threading.Thread(target=late)
            worker.start()
            assert blocked_on(owner_conn, second.info.backend_pid, first.info.backend_pid)
        worker.join(10)
    [answer] = outcome
    assert isinstance(answer, psycopg.Error)
    assert (answer.sqlstate, answer.diag.message_primary) == ("XC409", "expense_version_conflict")
    current = detail(answer)["current"]
    assert (current["id"], current["version"], num(current["total"]), current["source"]) == (
        str(row_id),
        2,
        450,
        "central",
    )
    assert (current["can_edit"], current["registration"]) == (True, "KDA 103A")
    assert stored(owner_conn, row_id)["unit_amount"] == 450


def test_a_conflict_on_a_row_the_ledger_cannot_list_carries_a_null_current(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    row_id = insert_row(owner_conn, depot, depot.kda, day(-61), 500)
    error = refuses(
        app_conn,
        "expenses_entry_remove",
        depot.admin,
        [row_id, 9, "Before it joined"],
        "XC409",
        "expense_version_conflict",
    )
    assert detail(error) == {"current": None}


# --- remove a row ---


def test_the_remove_steps_answer_in_their_order(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, depot: Depot
) -> None:
    viewer = provision_member(operator_conn, 4, "Fleet manager", "Grace", "Wambui")
    admins = one(app_conn, depot, 500)
    hidden = one(app_conn, depot, 500, vehicle=depot.kdc)
    own_earlier = insert_row(owner_conn, depot, depot.kda, day(-1), 500, by=depot.clerk)

    def refused(who: Member, args: list[Any], sqlstate: str, code: str) -> psycopg.Error:
        return refuses(app_conn, "expenses_entry_remove", who, args, sqlstate, code)

    refused(viewer, [admins, 1, "x"], "XC403", "permission_missing")
    refused(depot.admin, [uuid4(), 1, None], "XC422", "reason_length")
    refused(depot.admin, [uuid4(), 1, "   "], "XC422", "reason_length")
    refused(depot.admin, [uuid4(), 1, "r" * 501], "XC422", "reason_length")
    refused(depot.admin, [uuid4(), 1, "r" * 500], "XC404", "not_found")
    refused(depot.clerk, [hidden, 1, "Mine?"], "XC404", "not_found")
    refused(depot.clerk, [admins, 1, "Mine?"], "XC403", "expense_change_other")
    refused(depot.clerk, [own_earlier, 1, "Late"], "XC403", "expense_change_earlier_day")
    old = insert_row(owner_conn, depot, depot.kda, day(-5), 500)
    set_back_limit(owner_conn, depot.admin, 2)
    refused(depot.admin, [old, None, "Closed"], "XC422", "record_too_old")
    refused(depot.admin, [admins, None, "Twice"], "XC422", "expense_version_required")
    error = refused(depot.admin, [admins, 2, "Twice"], "XC409", "expense_version_conflict")
    assert detail(error)["current"]["id"] == str(admins)
    assert remove(app_conn, depot.admin, admins, 1, "  Twice ") == {"id": str(admins), "version": 2}
    refused(depot.admin, [admins, 2, "Again"], "XC404", "not_found")


def test_removing_takes_the_row_out_of_every_list_and_logs_the_reason(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    kept = one(app_conn, depot, 1500)
    gone = one(app_conn, depot, 4000)
    remove(app_conn, depot.admin, gone, 1, "Recorded twice")
    row = stored(owner_conn, gone)
    assert (row["removed_by"], row["removed_at"], row["removal_reason"], row["version"]) == (
        depot.admin.id,
        T0,
        "Recorded twice",
        2,
    )
    assert reasons(owner_conn, depot)[-1] == (
        "Removed central expense on KDA 103A for 9 Oct 2026: Tyres, KES 4,000."
        " Reason: Recorded twice."
    )
    seen = ledger(app_conn, depot.admin)
    assert [i["id"] for i in seen["items"]] == [str(kept)]
    assert (num(seen["figures"]["central"]), num(seen["amount"])) == (1500, 1500)
    report = read(app_conn, "setup_vehicle_report", depot.owner, depot.kda, None, day(-1), TODAY)
    central = [p for p in report["postings"] if p.get("source") == "central"]
    assert [p["version_id"] for p in central] == [str(kept)]
    refuses(
        app_conn,
        "expenses_entry_update",
        depot.admin,
        change_args(
            gone, on=TODAY, vehicle=depot.kda, item=depot.tyres, units=1, unit_amount=1, version=2
        ),
        "XC404",
        "not_found",
    )


def test_capture_alone_changes_only_its_own_rows_of_the_day_and_correct_any(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    mine = one(app_conn, depot, 300, who=depot.clerk)
    theirs = one(app_conn, depot, 300)
    yesterday = insert_row(owner_conn, depot, depot.kda, day(-1), 300, by=depot.clerk)
    seen = {
        i["id"]: (i["can_edit"], i["can_remove"]) for i in ledger(app_conn, depot.clerk)["items"]
    }
    assert seen == {
        str(mine): (True, True),
        str(theirs): (False, False),
        str(yesterday): (False, False),
    }
    remove(app_conn, depot.clerk, mine, 1, "Mine, today")
    for row_id in (theirs, yesterday):
        assert remove(app_conn, depot.admin, row_id, 1, "Corrected")["version"] == 2


# --- the back-dating limit ---


def test_a_central_expense_before_the_limit_is_refused_on_record_change_and_remove(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    """Record checks the date, a change the stored and the new date, remove the date; a row
    before the limit also shows no edit or remove flag."""
    today_row = one(app_conn, depot, 200)
    old = insert_row(owner_conn, depot, depot.kda, day(-3), 200)
    set_back_limit(owner_conn, depot.admin, 2)
    record_refused(
        app_conn,
        depot,
        purchase_args(depot, 1, 200, [(depot.kda, 200)], on=day(-3)),
        "XC422",
        "record_too_old",
    )
    record(app_conn, depot, 1, 200, [(depot.kda, 200)], on=day(-2))
    refuses(
        app_conn,
        "expenses_entry_update",
        depot.admin,
        change_args(old, on=TODAY, vehicle=depot.kda, item=depot.tyres, units=1, unit_amount=250),
        "XC422",
        "record_too_old",
    )
    refuses(
        app_conn,
        "expenses_entry_update",
        depot.admin,
        change_args(
            today_row, on=day(-3), vehicle=depot.kda, item=depot.tyres, units=1, unit_amount=200
        ),
        "XC422",
        "record_too_old",
    )
    refuses(
        app_conn,
        "expenses_entry_remove",
        depot.admin,
        [old, 1, "Closed day"],
        "XC422",
        "record_too_old",
    )
    flags = {i["id"]: i["can_edit"] for i in ledger(app_conn, depot.admin)["items"]}
    assert (flags[str(old)], flags[str(today_row)]) == (False, True)


# --- the ledger ---


@pytest.mark.parametrize(
    ("start", "end", "source", "q", "page", "size", "code"),
    [
        (None, None, "bogus", "q" * 201, 0, 100, "page_out_of_range"),
        (None, None, "bogus", "q" * 201, 1, 101, "page_out_of_range"),
        (None, TODAY, "bogus", "q" * 201, 1, 100, "expense_period_required"),
        (TODAY, None, "bogus", "q" * 201, 1, 100, "expense_period_required"),
        (TODAY, day(-1), "bogus", "q" * 201, 1, 100, "expense_period_order"),
        (day(-367), TODAY, "bogus", "q" * 201, 1, 100, "expense_period_length"),
        (day(-366), TODAY, "bogus", "q" * 201, 1, 100, "expense_source_invalid"),
        (day(-366), TODAY, "central", "q" * 201, 1, 100, "expense_search_length"),
    ],
)
def test_the_ledger_checks_its_query_in_order(
    app_conn: Conn,
    depot: Depot,
    start: date | None,
    end: date | None,
    source: str,
    q: str,
    page: int,
    size: int,
    code: str,
) -> None:
    refuses(
        app_conn,
        "expenses_ledger_get",
        depot.clerk,
        [start, end, source, q, page, size],
        "XC422",
        code,
    )


def test_the_ledger_needs_its_view_right_and_takes_any_source_word_case(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, depot: Depot
) -> None:
    driver = provision_member(operator_conn, 4, "Fleet manager", "Grace", "Wambui")
    set_override(owner_conn, driver, "expenses.view", False)
    refuses(
        app_conn,
        "expenses_ledger_get",
        driver,
        [TODAY, TODAY, None, None, 1, 100],
        "XC403",
        "permission_missing",
    )
    seen = ledger(app_conn, depot.clerk, source=" PettyCash ", q="  " + "q" * 200 + "  ")
    assert (seen["total"], seen["items"]) == (0, [])


def test_the_ledger_lists_three_sources_newest_first_and_never_savings(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    central = one(app_conn, depot, 4000, note="Front pair")
    shared = record(app_conn, depot, 2, 500, [(depot.kdb, 500), (depot.kda, 500)], on=day(-1))
    petty = petty_expense(owner_conn, depot, depot.kda, day(-1), 300, note="Top up")
    petty_expense(owner_conn, depot, depot.kda, day(-1), 999, status=1)
    insurance, _ = add_schedule(
        owner_conn,
        depot.org,
        Version(
            day(-40),
            {depot.kda: Decimal(700)},
            name="Insurance",
            day=5,
            expense_item_id=depot.tyres,
            bucket=3,
            note="Monthly cover",
        ),
    )
    add_schedule(
        owner_conn,
        depot.org,
        Version(day(-40), {depot.kda: Decimal(900)}, name="Rainy day", kind=2, day=5),
    )
    seen = ledger(app_conn, depot.owner, day(-40))
    rows = seen["items"]
    assert [(r["source"], r["entry_date"], r["registration"]) for r in rows] == [
        ("central", "2026-10-09", "KDA 103A"),
        ("central", "2026-10-08", "KDA 103A"),
        ("central", "2026-10-08", "KDB 204B"),
        ("pettycash", "2026-10-08", "KDA 103A"),
        ("scheduled", "2026-10-05", "KDA 103A"),
        ("scheduled", "2026-09-05", "KDA 103A"),
    ]
    assert seen["figures"] == {"total": 6700, "central": 5000, "petty_cash": 300, "scheduled": 1400}
    assert (seen["total"], num(seen["amount"]), seen["page_number"], seen["page_size"]) == (
        6,
        6700,
        1,
        100,
    )
    assert (seen["business_date"], seen["from_date"], seen["to_date"]) == (
        "2026-10-09",
        "2026-08-30",
        "2026-10-09",
    )
    assert seen["permissions"] == {"can_record": True, "can_correct": True}
    first = rows[0]
    assert first == {
        "id": str(central),
        "source": "central",
        "entry_date": "2026-10-09",
        "vehicle_id": str(depot.kda),
        "registration": "KDA 103A",
        "expense_item_id": str(depot.tyres),
        "item_name": "Tyres",
        "category_name": "Repairs",
        "bucket": 1,
        "units": 1.0,
        "unit_amount": 4000.0,
        "total": 4000.0,
        "note": "Front pair",
        "recorded_by_name": "Peter Otieno",
        "holder_name": None,
        "schedule_id": None,
        "group": None,
        "version": 1,
        "can_edit": True,
        "can_remove": True,
        "main_category_name": "Running",
        "fleet_number": "N-01",
    } | {k: first[k] for k in ("units", "unit_amount", "total")}
    assert (num(first["units"]), num(first["total"])) == (1, 4000)
    group = rows[1]["group"]
    assert (group["id"], group["size"], num(group["total"]), num(group["units"])) == (
        str(stored(owner_conn, UUID(shared["ids"][0]))["group_id"]),
        2,
        1000,
        2,
    )
    petty_row = rows[3]
    assert (
        petty_row["id"],
        petty_row["item_name"],
        petty_row["category_name"],
        petty_row["bucket"],
        petty_row["holder_name"],
        petty_row["recorded_by_name"],
        petty_row["version"],
        petty_row["can_edit"],
        petty_row["main_category_name"],
    ) == (str(petty), "Diesel", "Fuelling", 2, "Wanjiru Kamau", "Wanjiru Kamau", None, False, None)
    scheduled = rows[4]
    assert (
        scheduled["id"],
        scheduled["schedule_id"],
        scheduled["item_name"],
        scheduled["category_name"],
        scheduled["bucket"],
        num(scheduled["units"]),
        num(scheduled["total"]),
        scheduled["note"],
        scheduled["recorded_by_name"],
        scheduled["holder_name"],
        scheduled["version"],
        scheduled["can_edit"],
        scheduled["can_remove"],
        scheduled["expense_item_id"],
    ) == (
        f"{insurance}:2026-10-05:{depot.kda}",
        str(insurance),
        "Insurance",
        "Repairs",
        3,
        1,
        700,
        "Monthly cover",
        None,
        None,
        None,
        False,
        False,
        str(depot.tyres),
    )


def test_source_and_search_narrow_the_rows_not_the_figures(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    one(app_conn, depot, 100, note="50% off_sale \\ cash")
    one(app_conn, depot, 200, vehicle=depot.kdb, item=depot.fuel, note="10% less")
    petty_expense(owner_conn, depot, depot.kda, TODAY, 300)
    add_schedule(
        owner_conn,
        depot.org,
        Version(day(-40), {depot.kdb: Decimal(400)}, name="Parking permit", day=5),
    )
    figures = {"total": 1400, "central": 300, "petty_cash": 300, "scheduled": 800}

    def found(**kw: Any) -> tuple[int, Decimal, list[str]]:
        seen = ledger(app_conn, depot.owner, day(-40), **kw)
        assert seen["figures"] == figures
        return seen["total"], num(seen["amount"]), [r["source"] for r in seen["items"]]

    assert found(source="central") == (2, Decimal(300), ["central", "central"])
    assert found(source="scheduled") == (2, Decimal(800), ["scheduled", "scheduled"])
    assert found(q="kdb") == (3, Decimal(1000), ["central", "scheduled", "scheduled"])
    assert found(q="diesel")[0:2] == (2, Decimal(500))
    assert found(q="fuelLING")[0:2] == (2, Decimal(500))
    assert found(q="% off_")[0:2] == (1, Decimal(100))
    assert found(q="\\ cash")[0:2] == (1, Decimal(100))
    assert found(q="\\")[0:2] == (1, Decimal(100))
    assert found(q="%")[0:2] == (2, Decimal(300))
    assert found(q="0%")[0:2] == (2, Decimal(300))
    assert found(q="0_")[0:2] == (0, Decimal(0))
    assert found(q="peter")[0:2] == (2, Decimal(300))
    assert found(q="wanjiru") == (1, Decimal(300), ["pettycash"])
    assert found(q="permit", source="central") == (0, Decimal(0), [])
    assert found(q="parking")[0:2] == (2, Decimal(800))
    assert found(q="' OR 1=1 --")[0:2] == (0, Decimal(0))


def test_pages_are_cut_in_the_ledgers_order(app_conn: Conn, owner_conn: Conn, depot: Depot) -> None:
    for offset, vehicle in ((0, depot.kdb), (0, depot.kda), (-1, depot.kda), (-2, depot.kdc)):
        insert_row(owner_conn, depot, vehicle, day(offset), 100)
    petty_expense(owner_conn, depot, depot.kda, TODAY, 50)
    whole = [
        (r["entry_date"], r["source"], r["registration"])
        for r in ledger(app_conn, depot.owner)["items"]
    ]
    assert whole == [
        ("2026-10-09", "central", "KDA 103A"),
        ("2026-10-09", "central", "KDB 204B"),
        ("2026-10-09", "pettycash", "KDA 103A"),
        ("2026-10-08", "central", "KDA 103A"),
        ("2026-10-07", "central", "KDC 305C"),
    ]
    pages = [ledger(app_conn, depot.owner, page=n, size=2) for n in (1, 2, 3, 4)]
    assert [
        [(r["entry_date"], r["source"], r["registration"]) for r in p["items"]] for p in pages
    ] == [
        whole[0:2],
        whole[2:4],
        whole[4:5],
        [],
    ]
    assert {(p["total"], num(p["amount"])) for p in pages} == {(5, Decimal(450))}


_LEDGER_ROWS_CUT = """
WITH a AS (
  SELECT tenancy.business_date(%(org)s, %(now)s) AS today,
         tenancy.effective_permissions(%(org)s, %(actor)s) AS rights
),
r AS MATERIALIZED (
  SELECT x.*
  FROM a,
       expenses.ledger_rows(
         ARRAY(SELECT v.id FROM setup.visible_vehicles() AS v (id)), %(start)s, %(end)s, a.today,
         %(source)s, %(q)s, %(actor)s, 'expenses.capture' = ANY (a.rights),
         'expenses.correct' = ANY (a.rights), tenancy.earliest_writable(%(org)s, %(actor)s, a.today)
       ) AS x
)
SELECT jsonb_build_object(
  'figures', (
    SELECT jsonb_build_object(
      'total', coalesce(sum(r.total), 0),
      'central', coalesce(sum(r.total) FILTER (WHERE r.source_order = 1), 0),
      'petty_cash', coalesce(sum(r.total) FILTER (WHERE r.source_order = 2), 0),
      'scheduled', coalesce(sum(r.total) FILTER (WHERE r.source_order = 3), 0))
    FROM r),
  'items', (
    SELECT coalesce(jsonb_agg(to_jsonb(p) - 'source_order' - 'matched'
             ORDER BY p.entry_date DESC, p.source_order, p.registration COLLATE "C",
                      p.id COLLATE "C"),
             '[]'::jsonb)
    FROM (SELECT r.* FROM r WHERE r.matched
          ORDER BY r.entry_date DESC, r.source_order, r.registration COLLATE "C", r.id COLLATE "C"
          OFFSET %(offset)s LIMIT %(size)s) AS p),
  'total', (SELECT count(*) FROM r WHERE r.matched),
  'amount', (SELECT coalesce(sum(r.total), 0) FROM r WHERE r.matched)
) AS r
"""


def test_every_page_is_the_ledger_rows_helper_cut_in_the_ledgers_order(
    app_conn: Conn, owner_conn: Conn, executor: Conn, depot: Depot
) -> None:
    """The route reads its figures, count and page from the postings and builds only the page's
    rows; whatever the viewer, source, search or page, its answer is what the whole period of
    ``expenses.ledger_rows`` (the export's and the saved row's helper) gives, cut in the ledger's
    order: many rows on one vehicle and day ordered by id, three schedules on one vehicle and day,
    a shared purchase, a removed row, a pending petty-cash expense and the clerk's own row."""
    for vehicle, offset, count in ((depot.kda, 0, 6), (depot.kdb, 0, 3), (depot.kdc, -1, 2)):
        for n in range(count):
            insert_row(owner_conn, depot, vehicle, day(offset), 10 * (n + 1))
    insert_row(owner_conn, depot, depot.kda, day(-3), 40, note="Front pair")
    record(app_conn, depot, 2, 500, [(depot.kdb, 500), (depot.kda, 500)], on=day(-1))
    one(app_conn, depot, 50, who=depot.clerk)
    gone = one(app_conn, depot, 70)
    remove(app_conn, depot.admin, gone, 1, "Twice")
    petty_expense(owner_conn, depot, depot.kda, TODAY, 300, note="Top up")
    petty_expense(owner_conn, depot, depot.kdc, day(-1), 120)
    petty_expense(owner_conn, depot, depot.kda, TODAY, 999, status=1)
    for name in ("Insurance", "Tracking"):
        add_schedule(
            owner_conn,
            depot.org,
            Version(
                day(-40), {depot.kda: Decimal(25)}, name=name, day=5, expense_item_id=depot.tyres
            ),
        )
    add_schedule(
        owner_conn,
        depot.org,
        Version(
            day(-40),
            {depot.kda: Decimal(10), depot.kdb: Decimal(20), depot.kdc: Decimal(30)},
            name="Parking",
            day=5,
        ),
    )
    filters: list[dict[str, Any]] = [
        {},
        {"source": "central"},
        {"source": "scheduled"},
        {"q": "kd"},
        {"q": "a 1"},
        {"q": "wanjiru"},
        {"q": "peter", "source": "central"},
    ]
    size = 3
    seen_rows = 0
    for who in (depot.owner, depot.clerk):
        for kw in filters:
            source, q = kw.get("source"), kw.get("q")
            page = 1
            while True:
                got = ledger(app_conn, who, day(-40), source=source, q=q, page=page, size=size)
                with executor.transaction():
                    executor.execute(
                        "SELECT tenancy.enter_organization(%s, %s, 'req-ledger-parity', NULL)",
                        (who.id, who.org),
                    )
                    row = executor.execute(
                        _LEDGER_ROWS_CUT,
                        {
                            "org": who.org,
                            "actor": who.id,
                            "now": T0,
                            "start": day(-40),
                            "end": TODAY,
                            "source": source,
                            "q": q,
                            "offset": (page - 1) * size,
                            "size": size,
                        },
                    ).fetchone()
                assert row is not None
                assert {k: got[k] for k in ("figures", "items", "total", "amount")} == row["r"], (
                    who.first_name,
                    kw,
                    page,
                )
                seen_rows += len(got["items"])
                if not got["items"]:
                    break
                page += 1
    assert seen_rows > 60


def test_nothing_counts_after_the_business_date_or_outside_a_vehicles_days(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    add_schedule(
        owner_conn,
        depot.org,
        Version(day(-40), {depot.kda: Decimal(700)}, name="Insurance", day=12),
    )
    insert_row(owner_conn, depot, depot.kda, day(-61), 900)
    left = add_vehicle(
        owner_conn, depot.org, depot.north, "KDF 608F", joined_on=day(-30), left_on=day(-5)
    )
    insert_row(owner_conn, depot, left, day(-6), 10)
    insert_row(owner_conn, depot, left, day(-5), 20)
    add_away(owner_conn, depot.org, depot.kdb, day(-3), day(-1))
    insert_row(owner_conn, depot, depot.kdb, day(-2), 30)
    seen = ledger(app_conn, depot.owner, day(-90), day(30))
    assert [(r["entry_date"], num(r["total"])) for r in seen["items"]] == [
        ("2026-10-07", 30),
        ("2026-10-03", 10),
        ("2026-09-12", 700),
    ]
    later = ledger(app_conn, depot.owner, day(1), day(30))
    assert (later["items"], later["total"], later["figures"]["total"]) == ([], 0, 0)


def test_the_ledger_figures_of_a_scoped_viewer_leave_out_hidden_vehicles(
    app_conn: Conn, owner_conn: Conn, depot: Depot
) -> None:
    one(app_conn, depot, 100)
    one(app_conn, depot, 200, vehicle=depot.kdc)
    petty_expense(owner_conn, depot, depot.kdc, TODAY, 300)
    add_schedule(
        owner_conn,
        depot.org,
        Version(day(-40), {depot.kda: Decimal(40), depot.kdc: Decimal(60)}, name="Tracking", day=5),
    )
    whole = ledger(app_conn, depot.owner, day(-40))
    scoped = ledger(app_conn, depot.clerk, day(-40))
    assert whole["figures"] == {"total": 800, "central": 300, "petty_cash": 300, "scheduled": 200}
    assert scoped["figures"] == {"total": 180, "central": 100, "petty_cash": 0, "scheduled": 80}
    assert {r["registration"] for r in scoped["items"]} == {"KDA 103A"}
    assert (scoped["total"], num(scoped["amount"])) == (3, 180)
    assert scoped["permissions"] == {"can_record": True, "can_correct": False}


# --- the options ---


def test_the_options_follow_the_rights_the_scope_and_the_date(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, depot: Depot
) -> None:
    viewer = provision_member(operator_conn, 4, "Fleet manager", "Grace", "Wambui")
    refuses(app_conn, "expenses_options_get", viewer, [None], "XC403", "permission_missing")
    refuses(app_conn, "expenses_options_get", depot.clerk, [day(1)], "XC422", "expense_date_future")
    refuses(
        app_conn, "expenses_options_get", depot.clerk, [day(-3651)], "XC422", "expense_date_too_old"
    )
    add_away(owner_conn, depot.org, depot.kdb, day(-3), day(-1))
    add_vehicle(owner_conn, depot.org, depot.north, "KDG 709G", joined_on=day(1))
    add_item(owner_conn, depot.org, depot.repairs, "Rims", stopped_on=day(-1))
    seen = read(app_conn, "expenses_options_get", depot.clerk, None)
    assert seen["vehicles"] == [
        {
            "id": str(depot.kda),
            "company_id": str(depot.north),
            "company_name": "North Fleet",
            "registration": "KDA 103A",
            "active": True,
            "fleet_number": "N-01",
        },
        {
            "id": str(depot.kdb),
            "company_id": str(depot.north),
            "company_name": "North Fleet",
            "registration": "KDB 204B",
            "active": True,
            "fleet_number": None,
        },
    ]
    assert [
        (i["name"], i["category_name"], i["bucket"], i["main_category_name"]) for i in seen["items"]
    ] == [
        ("Diesel", "Fuelling", 2, None),
        ("Tyres", "Repairs", 1, "Running"),
    ]
    earlier = read(app_conn, "expenses_options_get", depot.admin, day(-2))
    assert [v["registration"] for v in earlier["vehicles"]] == ["KDA 103A", "KDC 305C"]
    assert [i["name"] for i in earlier["items"]] == ["Diesel", "Rims", "Tyres"]
