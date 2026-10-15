"""The target set routines (``api.setup_target_set_*``), called as ``xcode_app``: the list of a
vehicle's sets newest first, a set from today or later that replaces the set of its date or adds
one, the set equal to the one in force refused, sets that have started kept (one starting today
may still be replaced, not removed), the change-log sentences and snapshots, the check order,
and the rights: ``vehicles.view`` to read, ``vehicles.target`` to save and remove. Two saves
racing on one vehicle are in ``test_setup_races``; other organizations and data scopes in
``test_setup_object_authorization``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from ..support.scenario import Conn
from ..support.setup_rows import (
    add_target,
    add_target_set,
    change_rows,
    read,
    reasons,
    refuses,
    run,
)
from ..support.tenancy import (
    Member,
    add_company,
    add_vehicle,
    provision_member,
    set_organization,
    set_override,
    set_scope,
    settings_version,
)

TODAY = date(2026, 3, 5)
WEEK = [Decimal(d) for d in ("1000", "1000", "1000", "1000", "1000", "1500", "500")]
LATER = [Decimal(d) for d in ("1200", "1200", "1200", "1200", "1200.50", "1800", "600")]


@dataclass(frozen=True, slots=True)
class Yard:
    owner: Member
    clerk: Member
    kda: UUID


@pytest.fixture
def yard(operator_conn: Conn, owner_conn: Conn) -> Yard:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 2, "Revenue clerk", "Cleo", "Clerk")
    set_organization(owner_conn, owner.org, business_date=TODAY)
    north = add_company(owner_conn, owner.org, "North Star")
    kda = add_vehicle(owner_conn, owner.org, north, "KDA 482M", fleet_number="N-1")
    add_target(owner_conn, owner.org, kda, 1, date(2026, 1, 1), 7000)
    return Yard(owner=owner, clerk=clerk, kda=kda)


def _holding(operator_conn: Conn, owner_conn: Conn, slot: int, *rights: str) -> Member:
    who = provision_member(operator_conn, slot, "Revenue clerk", "Sam", f"Rights{slot}")
    for right in rights:
        set_override(owner_conn, who, right)
    set_scope(owner_conn, who, who.org, all_companies=True)
    return who


def _save(app_conn: Conn, who: Member, vehicle: UUID, starts_on: Any, days: Any) -> dict[str, Any]:
    return run(app_conn, "setup_target_set_save", who, vehicle, starts_on, days)


def _sets(owner_conn: Conn, vehicle: UUID) -> list[tuple[date, list[Decimal]]]:
    rows = owner_conn.execute(
        "SELECT starts_on, ARRAY[monday, tuesday, wednesday, thursday, friday, saturday, "
        "sunday] AS days FROM setup.vehicle_target_sets WHERE vehicle_id = %s ORDER BY starts_on",
        (vehicle,),
    ).fetchall()
    return [(r["starts_on"], r["days"]) for r in rows]


SEVEN = [Decimal(1000)] * 7


# --- list ------------------------------------------------------------------------------


def test_the_list_is_newest_first_with_the_set_in_force_and_those_that_can_go(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    in_force = add_target_set(owner_conn, org, yard.kda, date(2026, 3, 2), WEEK)
    later = add_target_set(owner_conn, org, yard.kda, date(2026, 3, 20), LATER)
    sets = read(app_conn, "setup_target_set_list", yard.owner, yard.kda)
    assert [(s["starts_on"], s["in_force"], s["can_remove"]) for s in sets] == [
        ("2026-03-20", False, True),
        ("2026-03-02", True, False),
        ("2026-01-01", False, False),
    ]
    assert sets[0] == {
        "id": str(later),
        "starts_on": "2026-03-20",
        "days": [1200, 1200, 1200, 1200, 1200.50, 1800, 600],
        "week_total": 8400.50,
        "in_force": False,
        "can_remove": True,
    }
    assert (sets[1]["id"], sets[1]["week_total"]) == (str(in_force), 7000)
    viewer = _holding(operator_conn, owner_conn, 3, "vehicles.view")
    seen = read(app_conn, "setup_target_set_list", viewer, yard.kda)
    assert [s["can_remove"] for s in seen] == [False, False, False]


def test_a_set_starting_today_is_in_force_and_cannot_be_removed(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    add_target_set(owner_conn, yard.owner.org, yard.kda, TODAY, WEEK)
    newest, oldest = read(app_conn, "setup_target_set_list", yard.owner, yard.kda)
    assert (newest["starts_on"], newest["in_force"], newest["can_remove"]) == (
        "2026-03-05",
        True,
        False,
    )
    assert oldest["in_force"] is False


def test_the_list_needs_vehicles_view_and_a_known_vehicle(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    investor = _holding(operator_conn, owner_conn, 3, "reports.investment", "companies.edit")
    for who in (yard.clerk, investor):
        refuses(app_conn, "setup_target_set_list", who, [yard.kda], "XC403", "permission_missing")
    setter = _holding(operator_conn, owner_conn, 4, "vehicles.target")
    assert len(read(app_conn, "setup_target_set_list", setter, yard.kda)) == 1
    refuses(app_conn, "setup_target_set_list", yard.owner, [UUID(int=1)], "XC404", "not_found")


# --- save ------------------------------------------------------------------------------


def test_a_future_set_is_added_and_logged_with_the_figures_before_and_after(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    before = settings_version(owner_conn, org)
    result = _save(app_conn, yard.owner, yard.kda, date(2026, 3, 20), LATER)
    assert (result["outcome"], result["version"]) == ("created", before + 1)
    assert _sets(owner_conn, yard.kda) == [(date(2026, 1, 1), SEVEN), (date(2026, 3, 20), LATER)]
    stored = owner_conn.execute(
        "SELECT id, created_by FROM setup.vehicle_target_sets WHERE starts_on = %s",
        (date(2026, 3, 20),),
    ).fetchone()
    assert stored == {"id": UUID(str(result["id"])), "created_by": yard.owner.id}
    (log,) = change_rows(owner_conn, org, "vehicles")
    assert (log["entity_id"], log["vehicle_id"], log["reason"]) == (
        yard.kda,
        yard.kda,
        "Target set, KDA 482M",
    )
    assert [s["StartsOn"] for s in json.loads(log["before"])["TargetSets"]] == ["2026-01-01"]
    assert json.loads(log["after"])["TargetSets"][1] == {
        "StartsOn": "2026-03-20",
        "Monday": 1200,
        "Tuesday": 1200,
        "Wednesday": 1200,
        "Thursday": 1200,
        "Friday": 1200.5,
        "Saturday": 1800,
        "Sunday": 600,
    }


def test_saving_again_on_the_same_date_replaces_the_set_that_has_not_started(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    first = _save(app_conn, yard.owner, yard.kda, date(2026, 3, 20), WEEK)
    second = _save(app_conn, yard.owner, yard.kda, date(2026, 3, 20), LATER)
    assert (second["id"], second["outcome"]) == (first["id"], "updated")
    assert _sets(owner_conn, yard.kda) == [(date(2026, 1, 1), SEVEN), (date(2026, 3, 20), LATER)]
    assert reasons(owner_conn, yard.owner.org, "vehicles") == ["Target set, KDA 482M"] * 2


def test_a_set_from_today_corrects_the_target_in_force_and_may_be_replaced_today(
    app_conn: Conn, owner_conn: Conn, executor: Conn, yard: Yard
) -> None:
    assert _save(app_conn, yard.owner, yard.kda, TODAY, WEEK)["outcome"] == "created"
    assert _save(app_conn, yard.owner, yard.kda, TODAY, LATER)["outcome"] == "updated"
    with executor.transaction():
        executor.execute(
            "SELECT tenancy.enter_organization(%s, %s, 'req', NULL)",
            (yard.owner.id, yard.owner.org),
        )
        row = executor.execute(
            "SELECT setup.day_target(%s, %s) AS t", (yard.kda, date(2026, 3, 6))
        ).fetchone()
    assert row == {"t": Decimal("1200.50")}


def test_a_set_cannot_start_in_the_past(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    refuses(
        app_conn,
        "setup_target_set_save",
        yard.owner,
        [yard.kda, date(2026, 3, 4), LATER],
        "XC422",
        "target_start_past",
    )
    assert _sets(owner_conn, yard.kda) == [(date(2026, 1, 1), SEVEN)]


@pytest.mark.parametrize("starts_on", [TODAY, date(2026, 3, 19)])
def test_a_set_equal_to_the_one_in_force_on_its_date_is_refused(
    app_conn: Conn, owner_conn: Conn, yard: Yard, starts_on: date
) -> None:
    add_target_set(owner_conn, yard.owner.org, yard.kda, date(2026, 3, 20), LATER)
    error = refuses(
        app_conn,
        "setup_target_set_save",
        yard.owner,
        [yard.kda, starts_on, SEVEN],
        "XC422",
        "target_set_unchanged",
    )
    assert json.loads(error.diag.message_detail or "") == {"date": starts_on.isoformat()}
    error = refuses(
        app_conn,
        "setup_target_set_save",
        yard.owner,
        [yard.kda, date(2026, 3, 25), LATER],
        "XC422",
        "target_set_unchanged",
    )
    assert json.loads(error.diag.message_detail or "") == {"date": "2026-03-25"}
    assert _save(app_conn, yard.owner, yard.kda, date(2026, 3, 19), LATER)["outcome"] == "created"
    assert change_rows(owner_conn, yard.owner.org, "vehicles")[-1]["reason"] == (
        "Target set, KDA 482M"
    )


def test_a_vehicle_that_left_takes_no_new_set(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s", (TODAY, yard.kda)
    )
    refuses(
        app_conn,
        "setup_target_set_save",
        yard.owner,
        [yard.kda, date(2026, 3, 20), LATER],
        "XC422",
        "vehicle_retired_edit",
    )


def test_a_save_checks_the_start_then_the_figures_then_the_vehicle(
    app_conn: Conn, yard: Yard
) -> None:
    owner = yard.owner
    for args, sqlstate, code in [
        ([UUID(int=1), None, None], "XC422", "target_start_required"),
        ([UUID(int=1), date(2020, 1, 1), WEEK[:6]], "XC422", "target_days_required"),
        ([UUID(int=1), date(2020, 1, 1), [*WEEK[:6], None]], "XC422", "target_days_required"),
        ([UUID(int=1), date(2020, 1, 1), [*WEEK[:6], Decimal(0)]], "XC422", "money_invalid"),
        ([UUID(int=1), date(2020, 1, 1), WEEK], "XC404", "not_found"),
        ([yard.kda, date(2020, 1, 1), WEEK], "XC422", "target_start_past"),
    ]:
        refuses(app_conn, "setup_target_set_save", owner, args, sqlstate, code)


def test_saving_and_removing_need_vehicles_target_alone(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    later = add_target_set(owner_conn, yard.owner.org, yard.kda, date(2026, 3, 20), LATER)
    editor = _holding(
        operator_conn, owner_conn, 3, "vehicles.view", "vehicles.add", "vehicles.edit"
    )
    for who in (yard.clerk, editor):
        refuses(
            app_conn,
            "setup_target_set_save",
            who,
            [yard.kda, date(2026, 3, 10), LATER],
            "XC403",
            "permission_missing",
        )
        refuses(app_conn, "setup_target_set_remove", who, [later], "XC403", "permission_missing")
    setter = _holding(operator_conn, owner_conn, 4, "vehicles.target")
    assert _save(app_conn, setter, yard.kda, date(2026, 3, 10), LATER)["outcome"] == "created"
    assert run(app_conn, "setup_target_set_remove", setter, later)["outcome"] == "updated"


# --- remove ----------------------------------------------------------------------------


def test_a_set_that_has_not_started_is_removed_and_logged(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    later = add_target_set(owner_conn, yard.owner.org, yard.kda, date(2026, 3, 6), LATER)
    result = run(app_conn, "setup_target_set_remove", yard.owner, later)
    assert (result["id"], result["outcome"]) == (later, "updated")
    assert _sets(owner_conn, yard.kda) == [(date(2026, 1, 1), SEVEN)]
    (log,) = change_rows(owner_conn, yard.owner.org, "vehicles")
    assert (log["vehicle_id"], log["reason"]) == (
        yard.kda,
        "Target removed before it started, KDA 482M",
    )
    assert [s["StartsOn"] for s in json.loads(log["before"])["TargetSets"]] == [
        "2026-01-01",
        "2026-03-06",
    ]
    assert json.loads(log["after"])["TargetSets"] == [
        {"StartsOn": "2026-01-01", **{day: 1000 for day in _DAYS}}
    ]
    refuses(app_conn, "setup_target_set_remove", yard.owner, [later], "XC404", "not_found")


_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@pytest.mark.parametrize("starts_on", [date(2026, 1, 1), TODAY])
def test_a_set_that_has_started_cannot_be_removed(
    app_conn: Conn, owner_conn: Conn, yard: Yard, starts_on: date
) -> None:
    started = add_target_set(owner_conn, yard.owner.org, yard.kda, starts_on, LATER)
    refuses(
        app_conn, "setup_target_set_remove", yard.owner, [started], "XC422", "target_set_started"
    )
    assert change_rows(owner_conn, yard.owner.org, "vehicles") == []
    refuses(app_conn, "setup_target_set_remove", yard.owner, [UUID(int=1)], "XC404", "not_found")
