"""Setup writes racing each other on two connections. The .NET API ran every setup write in a
serializable transaction; here each routine runs in READ COMMITTED, so a rule that reads one
row and writes another holds only if the routine locks the row it read. Each test lets the
first write hold its transaction open, starts the second on another connection, checks that
it waits, and then reads what both left behind."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from ..support.scenario import T0, Conn
from ..support.setup_rows import add_target
from ..support.tenancy import (
    REQUEST,
    Member,
    add_company,
    add_vehicle,
    provision_member,
    set_organization,
    write,
)

TODAY = date(2026, 3, 5)
WEEK = [Decimal(1000)] * 7


def _new(company: UUID, registration: str, fleet: str = "N-1") -> tuple[Any, ...]:
    """``api.setup_vehicle_create`` arguments after the standard three: from 2026-03-01."""
    return (company, registration, fleet, date(2026, 3, 1), WEEK, None, None)


@dataclass(frozen=True, slots=True)
class Yard:
    owner: Member
    north: UUID
    south: UUID


@pytest.fixture
def yard(operator_conn: Conn, owner_conn: Conn) -> Yard:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    set_organization(owner_conn, owner.org, business_date=TODAY)
    return Yard(
        owner=owner,
        north=add_company(owner_conn, owner.org, "North Star"),
        south=add_company(owner_conn, owner.org, "South Line"),
    )


def _race(
    app_url: str, first: Callable[[Conn], Any], late: Callable[[Conn], Any]
) -> tuple[Any, Any]:
    """Runs ``late`` on a second connection while ``first`` holds its transaction open."""
    results: list[Any] = []
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as one,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as two,
    ):
        started = threading.Event()

        def run_late() -> None:
            started.set()
            try:
                results.append(late(two))
            except psycopg.Error as error:
                results.append((error.sqlstate, error.diag.message_primary))

        with one.transaction():
            done = first(one)
            worker = threading.Thread(target=run_late)
            worker.start()
            assert started.wait(10)
            worker.join(0.5)
            assert worker.is_alive()
        worker.join(10)
    assert len(results) == 1
    return done, results[0]


def _call(routine: str, who: Member, *args: Any) -> Callable[[Conn], Any]:
    return lambda conn: write(conn, f"setup_{routine}", who.id, who.org, REQUEST, *args, T0)


def _vehicle(owner_conn: Conn, yard: Yard, company: UUID, **fields: Any) -> UUID:
    vehicle = add_vehicle(owner_conn, yard.owner.org, company, "KDA 482M", **fields)
    add_target(owner_conn, yard.owner.org, vehicle, 1, date(2026, 1, 1), 7000)
    return vehicle


def _company_of_active_vehicles(owner_conn: Conn, org: UUID) -> list[tuple[str, date | None]]:
    rows = owner_conn.execute(
        "SELECT c.name, c.archived_on FROM setup.fleet_vehicles AS f "
        "JOIN setup.psv_companies AS c ON c.organization_id = f.organization_id "
        "AND c.id = f.company_id "
        "WHERE f.organization_id = %s AND (f.left_on IS NULL OR f.left_on > %s) ORDER BY c.name",
        (org, TODAY),
    ).fetchall()
    return [(r["name"], r["archived_on"]) for r in rows]


def test_a_vehicle_added_while_its_company_is_archived_is_refused(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    first, late = _race(
        app_url,
        _call("company_archive", yard.owner, yard.north, None),
        _call("vehicle_create", yard.owner, *_new(yard.north, "KDA 482M")),
    )
    assert first["outcome"] == "updated"
    assert late == ("XC422", "vehicle_company_inactive")
    assert _company_of_active_vehicles(owner_conn, yard.owner.org) == []


def test_a_vehicle_moved_while_its_new_company_is_archived_is_refused(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    vehicle = _vehicle(owner_conn, yard, yard.south)
    first, late = _race(
        app_url,
        _call("company_archive", yard.owner, yard.north, None),
        _call(
            "vehicle_update",
            yard.owner,
            vehicle,
            yard.north,
            "KDA 482M",
            "N-1",
            date(2026, 1, 1),
            None,
            None,
        ),
    )
    assert first["outcome"] == "updated"
    assert late == ("XC422", "vehicle_company_inactive")
    assert _company_of_active_vehicles(owner_conn, yard.owner.org) == [("South Line", None)]


def test_a_vehicle_restored_while_its_company_is_archived_is_refused(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    vehicle = _vehicle(owner_conn, yard, yard.north, left_on=date(2026, 2, 1))
    first, late = _race(
        app_url,
        _call("company_archive", yard.owner, yard.north, None),
        _call("vehicle_restore", yard.owner, vehicle, None, None),
    )
    assert first["outcome"] == "updated"
    assert late == ("XC422", "vehicle_company_archived_restore")
    assert _company_of_active_vehicles(owner_conn, yard.owner.org) == []


def test_a_company_archived_while_a_vehicle_is_added_to_it_waits_and_is_refused(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    first, late = _race(
        app_url,
        _call("vehicle_create", yard.owner, *_new(yard.north, "KDA 482M")),
        _call("company_archive", yard.owner, yard.north, None),
    )
    assert first["outcome"] == "created"
    assert late == ("XC422", "company_has_vehicles")
    assert _company_of_active_vehicles(owner_conn, yard.owner.org) == [("North Star", None)]


def test_a_company_archived_while_its_vehicle_is_restored_waits_and_is_refused(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    vehicle = _vehicle(owner_conn, yard, yard.north, left_on=date(2026, 2, 1))
    first, late = _race(
        app_url,
        _call("vehicle_restore", yard.owner, vehicle, None, None),
        _call("company_archive", yard.owner, yard.north, None),
    )
    assert first["outcome"] == "updated"
    assert late == ("XC422", "company_has_vehicles")
    assert _company_of_active_vehicles(owner_conn, yard.owner.org) == [("North Star", None)]


def test_two_companies_with_one_name_racing_leave_one_row_and_a_unique_conflict(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    first, late = _race(
        app_url,
        _call("company_create", yard.owner, "East Line", None),
        _call("company_create", yard.owner, "EAST LINE", None),
    )
    assert first["outcome"] == "created"
    assert late[0] == "23505"
    rows = owner_conn.execute(
        "SELECT name FROM setup.psv_companies WHERE organization_id = %s AND normalized_name = %s",
        (yard.owner.org, "EAST LINE"),
    ).fetchall()
    assert [r["name"] for r in rows] == ["East Line"]


def test_two_vehicles_with_one_registration_racing_leave_one_row_and_a_unique_conflict(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    first, late = _race(
        app_url,
        _call("vehicle_create", yard.owner, *_new(yard.north, "KDA 482M")),
        _call("vehicle_create", yard.owner, *_new(yard.south, "kda482m", "S-1")),
    )
    assert first["outcome"] == "created"
    assert late[0] == "23505"
    assert _company_of_active_vehicles(owner_conn, yard.owner.org) == [("North Star", None)]


def test_two_vehicles_with_one_fleet_number_racing_leave_one_row_and_a_unique_conflict(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    first, late = _race(
        app_url,
        _call("vehicle_create", yard.owner, *_new(yard.north, "KDA 482M", "NS-7")),
        _call("vehicle_create", yard.owner, *_new(yard.north, "KDB 111A", "ns-7")),
    )
    assert first["outcome"] == "created"
    assert late[0] == "23505"
    rows = owner_conn.execute(
        "SELECT registration FROM setup.fleet_vehicles WHERE organization_id = %s",
        (yard.owner.org,),
    ).fetchall()
    assert [r["registration"] for r in rows] == ["KDA 482M"]


def _sets(owner_conn: Conn, vehicle: UUID) -> list[tuple[date, Decimal]]:
    rows = owner_conn.execute(
        "SELECT starts_on, monday FROM setup.vehicle_target_sets WHERE vehicle_id = %s "
        "ORDER BY starts_on",
        (vehicle,),
    ).fetchall()
    return [(r["starts_on"], r["monday"]) for r in rows]


def test_two_target_sets_saved_for_one_date_at_once_leave_the_later_one(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    vehicle = _vehicle(owner_conn, yard, yard.north)
    starts = date(2026, 3, 10)
    first, late = _race(
        app_url,
        _call("target_set_save", yard.owner, vehicle, starts, [Decimal(1100)] * 7),
        _call("target_set_save", yard.owner, vehicle, starts, [Decimal(1200)] * 7),
    )
    assert (first["outcome"], late["outcome"]) == ("created", "updated")
    assert first["id"] == late["id"]
    assert _sets(owner_conn, vehicle) == [
        (date(2026, 1, 1), Decimal(1000)),
        (starts, Decimal(1200)),
    ]


def test_a_target_set_saved_while_its_vehicle_leaves_waits_and_is_refused(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    vehicle = _vehicle(owner_conn, yard, yard.north)
    first, late = _race(
        app_url,
        _call("vehicle_retire", yard.owner, vehicle, TODAY, None),
        _call("target_set_save", yard.owner, vehicle, date(2026, 3, 10), [Decimal(1100)] * 7),
    )
    assert first["outcome"] == "updated"
    assert late == ("XC422", "vehicle_retired_edit")
    assert _sets(owner_conn, vehicle) == [(date(2026, 1, 1), Decimal(1000))]


def test_a_target_set_removed_while_it_is_replaced_waits_and_the_replacement_is_gone(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    vehicle = _vehicle(owner_conn, yard, yard.north)
    set_id = owner_conn.execute(
        "INSERT INTO setup.vehicle_target_sets (organization_id, vehicle_id, starts_on, monday, "
        "tuesday, wednesday, thursday, friday, saturday, sunday) "
        "VALUES (%s, %s, DATE '2026-03-10', 900, 900, 900, 900, 900, 900, 900) RETURNING id",
        (yard.owner.org, vehicle),
    ).fetchone()
    assert set_id is not None
    first, late = _race(
        app_url,
        _call("target_set_save", yard.owner, vehicle, date(2026, 3, 10), [Decimal(1100)] * 7),
        _call("target_set_remove", yard.owner, set_id["id"]),
    )
    assert (first["outcome"], late["outcome"]) == ("updated", "updated")
    assert _sets(owner_conn, vehicle) == [(date(2026, 1, 1), Decimal(1000))]
