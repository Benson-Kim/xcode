"""Day capture (``api.revenue_day_get``, ``api.revenue_day_save``), called as ``xcode_app``:
the day read (cell, last week, company, range, the 500 cap), the save's own checks, every row
through the single capture's steps, all or none, the 400 naming the vehicle, the conflict naming
it, two saves in opposite orders, and a saving run the day completes.

The business date is 9 Oct 2026, the date of ``T0`` in Nairobi; the low-day threshold is 100."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..support.scenario import T0, Conn, seed_10x
from ..support.setup_rows import (
    Version,
    add_away,
    add_record,
    add_schedule,
    add_target,
    read,
    refuses,
)
from ..support.tenancy import (
    REQUEST,
    Member,
    add_company,
    add_vehicle,
    change_log,
    provision_member,
    set_override,
    set_scope,
)

TODAY = date(2026, 10, 9)
OCT1 = date(2026, 10, 1)


@dataclass(frozen=True, slots=True)
class Yard:
    owner: Member
    clerk: Member
    north: UUID
    south: UUID
    kda: UUID
    kdb: UUID
    kdc: UUID


@pytest.fixture
def yard(operator_conn: Conn, owner_conn: Conn) -> Yard:
    """KDA 482M and KDB 111A of North Star, KDC 200B of South Line, all joined on 1 Oct."""
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 2, "Revenue clerk", "Cleo", "Clerk")
    org = owner.org
    set_scope(owner_conn, clerk, org, all_companies=True)
    owner_conn.execute(
        "INSERT INTO tenancy.organization_revenue_settings (organization_id, low_day_threshold, "
        "gap_amber_percent) VALUES (%s, 100, 10) ON CONFLICT (organization_id) DO UPDATE SET "
        "low_day_threshold = 100",
        (org,),
    )
    north = add_company(owner_conn, org, "North Star")
    south = add_company(owner_conn, org, "South Line")

    def vehicle(company: UUID, registration: str) -> UUID:
        vehicle_id = add_vehicle(owner_conn, org, company, registration, joined_on=OCT1)
        add_target(owner_conn, org, vehicle_id, 1, OCT1, 7000)
        return vehicle_id

    return Yard(
        owner=owner,
        clerk=clerk,
        north=north,
        south=south,
        kda=vehicle(north, "KDA 482M"),
        kdb=vehicle(north, "KDB 111A"),
        kdc=vehicle(south, "KDC 200B"),
    )


def _row(
    vehicle: UUID, amount: Any = None, reason: str | None = None, **more: Any
) -> dict[str, Any]:
    return {
        "vehicle_id": str(vehicle),
        "amount": None if amount is None else str(amount),
        "reason": reason,
        "note": more.get("note"),
        "version": None if more.get("version") is None else str(more["version"]),
    }


def _save(app: Conn, who: Member, day: date, *rows: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = read(app, "revenue_day_save", who, day, Jsonb(list(rows)))
    return result


def _refused(
    app: Conn, who: Member, day: date, rows: list[dict[str, Any]], sqlstate: str, code: str
) -> dict[str, Any]:
    error = refuses(app, "revenue_day_save", who, [day, Jsonb(rows)], sqlstate, code)
    text = error.diag.message_detail
    return json.loads(text) if text else {}


def _records(owner_conn: Conn, org: UUID, day: date) -> dict[UUID, Decimal | None]:
    rows = owner_conn.execute(
        "SELECT vehicle_id, amount FROM revenue.records WHERE organization_id = %s "
        "AND business_date = %s",
        (org, day),
    ).fetchall()
    return {UUID(str(r["vehicle_id"])): r["amount"] for r in rows}


def _day(app: Conn, who: Member, day: date | None = None, company: UUID | None = None) -> Any:
    return read(app, "revenue_day_get", who, day, company)


# --- the day read --------------------------------------------------------------------------


def test_the_day_lists_each_vehicle_with_its_cell_and_last_week(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    add_record(owner_conn, org, yard.kda, TODAY, 6500, recorder=yard.owner.id)
    add_record(owner_conn, org, yard.kda, TODAY - timedelta(days=7), 5000, recorder=yard.owner.id)
    add_record(
        owner_conn, org, yard.kdb, TODAY - timedelta(days=7), None, recorder=yard.owner.id, reason=1
    )
    day = _day(app_conn, yard.owner)
    assert (day["date"], day["business_date"], day["truncated"]) == (str(TODAY), str(TODAY), False)
    assert [v["registration"] for v in day["vehicles"]] == ["KDA 482M", "KDB 111A", "KDC 200B"]
    kda, kdb, kdc = day["vehicles"]
    assert (kda["day"]["status"], kda["day"]["amount"], kda["day"]["version"]) == (
        "amount",
        6500,
        1,
    )
    assert kda["last_week"] == {"amount": 5000, "reason": None}
    assert kdb["last_week"] == {"amount": None, "reason": "Garage"}
    assert (kdc["day"]["status"], kdc["last_week"]) == ("missing", None)
    assert set(kda) == {"id", "company_id", "registration", "fleet_number", "day", "last_week"}


def test_the_day_leaves_out_vehicles_away_or_out_of_the_fleet_and_follows_the_company(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    add_away(owner_conn, org, yard.kdb, TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s", (TODAY, yard.kdc)
    )
    assert [v["registration"] for v in _day(app_conn, yard.owner)["vehicles"]] == ["KDA 482M"]
    earlier = _day(app_conn, yard.owner, TODAY - timedelta(days=3))
    assert [v["registration"] for v in earlier["vehicles"]] == ["KDA 482M", "KDB 111A", "KDC 200B"]
    south = _day(app_conn, yard.owner, TODAY - timedelta(days=3), yard.south)
    assert [v["registration"] for v in south["vehicles"]] == ["KDC 200B"]


def test_a_day_after_today_or_more_than_ten_years_back_is_refused(
    app_conn: Conn, yard: Yard
) -> None:
    for day in (TODAY + timedelta(days=1), TODAY - timedelta(days=3651)):
        refuses(
            app_conn, "revenue_day_get", yard.owner, [day, None], "XC422", "revenue_day_date_range"
        )
    assert _day(app_conn, yard.owner, TODAY - timedelta(days=3650))["vehicles"] == []


def test_the_day_lists_at_most_500_vehicles_and_says_it_was_cut(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    owner_conn.execute(
        "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, joined_on) "
        "SELECT %s, %s, 'KZZ ' || lpad(g::text, 3, '0') || 'A', %s "
        "FROM generate_series(1, 498) AS g",
        (yard.owner.org, yard.north, OCT1),
    )
    day = _day(app_conn, yard.owner)
    assert (len(day["vehicles"]), day["truncated"]) == (500, True)
    assert day["vehicles"][-1]["registration"] == "KZZ 497A"


# --- the save --------------------------------------------------------------------------------


def test_the_save_answers_each_row_in_the_order_sent_and_logs_each_record(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    saved = _save(app_conn, yard.owner, TODAY, _row(yard.kdc, 900), _row(yard.kda, 700))
    assert [r["vehicle_id"] for r in saved["rows"]] == [str(yard.kdc), str(yard.kda)]
    assert all(r["version"] == 1 for r in saved["rows"])
    assert _records(owner_conn, yard.owner.org, TODAY) == {
        yard.kda: Decimal("700.00"),
        yard.kdc: Decimal("900.00"),
    }
    in_lock_order = sorted([(yard.kda, "KDA 482M"), (yard.kdc, "KDC 200B")])
    assert [r["reason"] for r in change_log(owner_conn, yard.owner.org)][-2:] == [
        f"Recorded revenue for {registration} on 9 Oct 2026" for _, registration in in_lock_order
    ]
    again = _save(app_conn, yard.owner, TODAY, _row(yard.kda, 700))
    assert again["rows"] == [
        {"vehicle_id": str(yard.kda), "id": saved["rows"][1]["id"], "version": 1}
    ]


@pytest.mark.parametrize(
    ("rows", "code"),
    [
        ([], "revenue_day_rows_required"),
        ("many", "revenue_day_rows_limit"),
        ("repeat", "revenue_day_vehicle_repeated"),
    ],
)
def test_the_save_checks_its_rows_first(app_conn: Conn, yard: Yard, rows: Any, code: str) -> None:
    if rows == "many":
        rows = [_row(UUID(int=n + 1), 500) for n in range(501)]
    elif rows == "repeat":
        rows = [_row(yard.kda, 500), {**_row(yard.kda, 600), "vehicle_id": str(yard.kda).upper()}]
    _refused(app_conn, yard.owner, TODAY, rows, "XC422", code)


def test_a_vehicle_out_of_reach_is_not_found_before_any_row_is_checked(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_scope(owner_conn, yard.clerk, yard.owner.org, companies=[yard.north])
    _refused(
        app_conn,
        yard.clerk,
        TODAY,
        [_row(yard.kda, "bad"), _row(yard.kdc, 500)],
        "XC404",
        "not_found",
    )
    _refused(app_conn, yard.owner, TODAY, [_row(UUID(int=7), 500)], "XC404", "not_found")


@pytest.mark.parametrize(
    ("row_of", "code"),
    [
        (lambda y: _row(y.kdb, None, None), "revenue_entry_required"),
        (lambda y: _row(y.kdb, "12.345"), "money_invalid"),
        (lambda y: _row(y.kdb, 500, "Other", note="x" * 81), "revenue_note_length"),
        (lambda y: _row(y.kdb, 50), "revenue_low_needs_reason"),
        (lambda y: _row(y.kdb, 500, "Garage"), "revenue_amount_with_reason"),
    ],
)
def test_a_refused_row_names_its_vehicle_and_saves_nothing_of_the_day(
    app_conn: Conn, owner_conn: Conn, yard: Yard, row_of: Any, code: str
) -> None:
    detail = _refused(
        app_conn, yard.owner, TODAY, [_row(yard.kda, 700), row_of(yard)], "XC422", code
    )
    assert detail["vehicle_registration"] == "KDB 111A"
    assert _records(owner_conn, yard.owner.org, TODAY) == {}


def test_each_row_runs_the_single_capture_rules(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    add_away(owner_conn, org, yard.kdb, TODAY - timedelta(days=2), TODAY)
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s",
        (TODAY - timedelta(days=1), yard.kdc),
    )
    day = TODAY - timedelta(days=1)
    assert (
        _refused(
            app_conn,
            yard.owner,
            TODAY + timedelta(days=1),
            [_row(yard.kda, 500)],
            "XC422",
            "revenue_future_date",
        )["vehicle_registration"]
        == "KDA 482M"
    )
    assert (
        _refused(app_conn, yard.owner, day, [_row(yard.kdb, 500)], "XC422", "revenue_vehicle_away")[
            "vehicle_registration"
        ]
        == "KDB 111A"
    )
    _refused(app_conn, yard.owner, day, [_row(yard.kdc, 500)], "XC422", "revenue_vehicle_inactive")
    for right in ("revenue.view", "revenue.correct"):
        set_override(owner_conn, yard.clerk, right)
    set_override(owner_conn, yard.clerk, "revenue.capture", granted=False)
    _refused(
        app_conn, yard.clerk, day, [_row(yard.kda, 500)], "XC403", "revenue_capture_permission"
    )
    saved = _save(app_conn, yard.owner, day, _row(yard.kda, 500))["rows"][0]
    set_override(owner_conn, yard.clerk, "revenue.capture")
    set_override(owner_conn, yard.clerk, "revenue.correct", granted=False)
    _refused(
        app_conn,
        yard.clerk,
        day,
        [_row(yard.kda, 600, version=1)],
        "XC403",
        "revenue_correct_permission",
    )
    assert _save(app_conn, yard.clerk, day, _row(yard.kda, 500))["rows"][0]["id"] == saved["id"]
    owner_conn.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = 'days', back_limit_count = 0 "
        "WHERE organization_id = %s AND user_id = %s",
        (org, yard.clerk.id),
    )
    _refused(
        app_conn,
        yard.clerk,
        day - timedelta(days=5),
        [_row(yard.kda, 700)],
        "XC422",
        "record_too_old",
    )


def test_a_stale_row_is_a_day_conflict_naming_the_vehicle_with_its_current_cell(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    _save(app_conn, yard.owner, TODAY, _row(yard.kda, 500))
    _save(app_conn, yard.owner, TODAY, _row(yard.kda, 650, version=1))
    detail = _refused(
        app_conn,
        yard.owner,
        TODAY,
        [_row(yard.kdb, 300), _row(yard.kda, 800, version=1)],
        "XC409",
        "revenue_day_conflict",
    )
    assert (detail["vehicle_id"], detail["registration"]) == (str(yard.kda), "KDA 482M")
    assert (detail["current"]["amount"], detail["current"]["version"]) == (650, 2)
    assert _records(owner_conn, yard.owner.org, TODAY) == {yard.kda: Decimal("650.00")}


def test_two_day_saves_in_opposite_orders_finish_without_a_deadlock(
    app_url: str, yard: Yard
) -> None:
    results: list[Any] = []

    def save(rows: list[dict[str, Any]]) -> None:
        with psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as conn:
            try:
                results.append(
                    conn.execute(
                        "SELECT api.revenue_day_save(%s, %s, %s, %s, %s, %s) AS r",
                        (yard.owner.id, yard.owner.org, REQUEST, TODAY, Jsonb(rows), T0),
                    ).fetchone()
                )
            except psycopg.Error as error:
                results.append((error.sqlstate, error.diag.message_primary))

    one = [_row(yard.kda, 500), _row(yard.kdb, 600), _row(yard.kdc, 700)]
    workers = [threading.Thread(target=save, args=(rows,)) for rows in (one, list(reversed(one)))]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
    assert len(results) == 2
    assert all(not (isinstance(r, tuple) and r[0] == "40P01") for r in results)


def test_a_day_save_that_completes_a_window_decides_the_saving_run(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    item, (version,) = add_schedule(
        owner_conn,
        org,
        Version(TODAY, {yard.kda: 400}, name="Fuel fund", kind=2, frequency=1, day=None),
    )
    owner_conn.execute(
        "UPDATE setup.recurring_versions SET condition_min = 1000, condition_days = 1 "
        "WHERE id = %s",
        (version,),
    )
    _save(app_conn, yard.owner, TODAY, _row(yard.kda, 1500), _row(yard.kdb, 200))
    rows = owner_conn.execute(
        "SELECT vehicle_id, run_on, state, revenue FROM setup.saving_runs WHERE item_id = %s",
        (item,),
    ).fetchall()
    assert [(UUID(str(r["vehicle_id"])), r["run_on"], r["state"], r["revenue"]) for r in rows] == [
        (yard.kda, TODAY, 1, Decimal("1500.00"))
    ]


def test_a_500_row_save_at_ten_times_the_fleet_fits_the_role_s_statement_timeout(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    assert seed_10x(owner_conn, org, 200) == 600
    owner_conn.execute("ANALYZE")
    ids = [
        r["id"]
        for r in owner_conn.execute(
            "SELECT id FROM setup.fleet_vehicles WHERE organization_id = %s "
            "ORDER BY registration LIMIT 500",
            (org,),
        ).fetchall()
    ]
    assert app_conn.execute("SHOW statement_timeout").fetchone() == {"statement_timeout": "5s"}
    first = _save(app_conn, yard.owner, TODAY, *[_row(i, 7000) for i in ids])
    assert len(first["rows"]) == 500
    again = _save(app_conn, yard.owner, TODAY, *[_row(i, 7000) for i in ids])
    assert again == first
    versions = {r["vehicle_id"]: r["version"] for r in first["rows"]}
    corrected = _save(
        app_conn,
        yard.owner,
        TODAY,
        *[_row(i, 6500, version=versions[str(i)]) for i in ids],
    )
    assert {r["version"] for r in corrected["rows"]} == {2}
    assert set(_records(owner_conn, org, TODAY).values()) == {Decimal("6500.00")}


def test_a_day_save_reads_the_rights_and_decides_the_saving_runs_once_per_call(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    url = make_conninfo(os.environ["XCODE_TEST_DATABASE_URL"], dbname=app_conn.info.dbname)
    rows = Jsonb([_row(yard.kda, 7000), _row(yard.kdb, 7000), _row(yard.kdc, 7000)])
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as admin:
        admin.execute("SET track_functions = 'all'")
        admin.execute("SELECT pg_stat_reset()")
        admin.execute("SET ROLE xcode_app")
        admin.execute(
            "SELECT api.revenue_day_save(%s, %s, %s, %s, %s, %s)",
            (yard.owner.id, yard.owner.org, REQUEST, TODAY, rows, T0),
        )
        admin.execute("RESET ROLE")
        admin.execute("SELECT pg_stat_force_next_flush()")
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as admin:
        calls = {
            r["name"]: r["calls"]
            for r in admin.execute(
                "SELECT schemaname || '.' || funcname AS name, calls FROM pg_stat_user_functions"
            ).fetchall()
        }
    assert len(_records(owner_conn, yard.owner.org, TODAY)) == 3
    assert calls.get("tenancy.effective_permissions") == 1
    assert calls.get("setup.scheduled_runs") == 1
    assert calls.get("tenancy.business_date", 0) <= 2
    assert calls.get("tenancy.earliest_writable") == 1


def test_a_row_past_the_back_dating_limit_names_the_earliest_day_and_the_vehicle(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_override(owner_conn, yard.clerk, "revenue.capture")
    owner_conn.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = 'days', back_limit_count = 2 "
        "WHERE organization_id = %s AND user_id = %s",
        (yard.owner.org, yard.clerk.id),
    )
    rows = [_row(yard.kdc, 700), _row(yard.kda, 700)]
    detail = _refused(
        app_conn, yard.clerk, TODAY - timedelta(days=3), rows, "XC422", "record_too_old"
    )
    assert detail == {
        "earliest": (TODAY - timedelta(days=2)).isoformat(),
        "vehicle_registration": min((yard.kda, "KDA 482M"), (yard.kdc, "KDC 200B"))[1],
    }
    saved = _save(app_conn, yard.clerk, TODAY - timedelta(days=2), *rows)
    assert len(saved["rows"]) == 2
