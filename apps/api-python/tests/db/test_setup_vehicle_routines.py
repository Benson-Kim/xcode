"""The vehicle routines (``api.setup_vehicle_*``, ``api.setup_company_options``), called as
``xcode_app``: one test per ``Raises:`` code, the ``unchanged`` no-ops, the list for managers
and investment viewers (the target set in force and the next one), the first target set from
the join date, edits that leave the targets alone (but for the backfill when the join date
moves before the first set), the fleet number and the initial investment, away periods on
restore, the automatic reasons byte for byte, the revenue-dated refusals, and the vehicle
report's window and figures. Target sets themselves are in ``test_setup_target_routines``.

Revenue records are seeded as ``xcode_owner``, without the capture routine; companies,
vehicles and scheduled items older than the business date are seeded the same way."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn
from ..support.setup_rows import (
    Version,
    add_away,
    add_record,
    add_schedule,
    add_target,
    add_target_set,
    change_rows,
    read,
    reasons,
    refuses,
    run,
    seed_report_fleet,
)
from ..support.tenancy import (
    REQUEST,
    Member,
    add_company,
    add_vehicle,
    provision_member,
    refused,
    set_localization,
    set_organization,
    set_override,
    set_scope,
    settings_version,
)

TODAY = date(2026, 3, 5)


@dataclass(frozen=True, slots=True)
class Yard:
    owner: Member
    clerk: Member
    north: UUID
    south: UUID


@pytest.fixture
def yard(operator_conn: Conn, owner_conn: Conn) -> Yard:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 2, "Revenue clerk", "Cleo", "Clerk")
    set_organization(owner_conn, owner.org, business_date=TODAY)
    return Yard(
        owner=owner,
        clerk=clerk,
        north=add_company(owner_conn, owner.org, "North Star"),
        south=add_company(owner_conn, owner.org, "South Line"),
    )


WEEK = [Decimal(d) for d in ("1000", "1000", "1000", "1000", "1000", "1500", "500")]


def _fleet(registration: str) -> str:
    return registration.replace(" ", "")[-4:]


def _vehicle(
    owner_conn: Conn, yard: Yard, registration: str = "KDA 482M", target: int = 7000, **fields: Any
) -> UUID:
    fields.setdefault("fleet_number", _fleet(registration))
    vehicle = add_vehicle(
        owner_conn, yard.owner.org, fields.pop("company", yard.north), registration, **fields
    )
    add_target(
        owner_conn, yard.owner.org, vehicle, 1, fields.get("joined_on", date(2026, 1, 1)), target
    )
    return vehicle


def _row(owner_conn: Conn, org: UUID, vehicle: UUID) -> dict[str, Any]:
    row = owner_conn.execute(
        "SELECT * FROM setup.fleet_vehicles WHERE organization_id = %s AND id = %s", (org, vehicle)
    ).fetchone()
    assert row is not None
    return row


def _targets(owner_conn: Conn, vehicle: UUID) -> list[tuple[date, list[Decimal]]]:
    rows = owner_conn.execute(
        "SELECT starts_on, ARRAY[monday, tuesday, wednesday, thursday, friday, saturday, "
        "sunday] AS days FROM setup.vehicle_target_sets WHERE vehicle_id = %s ORDER BY starts_on",
        (vehicle,),
    ).fetchall()
    return [(r["starts_on"], r["days"]) for r in rows]


def _away(owner_conn: Conn, vehicle: UUID) -> list[tuple[date, date]]:
    rows = owner_conn.execute(
        "SELECT left_on, returned_on FROM setup.vehicle_away_periods WHERE vehicle_id = %s "
        "ORDER BY left_on",
        (vehicle,),
    ).fetchall()
    return [(r["left_on"], r["returned_on"]) for r in rows]


def _save(
    company: UUID,
    registration: str,
    joined_on: date | None,
    days: Any = WEEK,
    fleet: str | None = "N-1",
    investment: Any = None,
) -> list[Any]:
    """The arguments of ``api.setup_vehicle_create`` between the standard three and the reason."""
    return [company, registration, fleet, joined_on, days, investment]


def _edit(
    company: UUID,
    registration: str,
    joined_on: date | None,
    fleet: str | None = "482M",
    investment: Any = None,
) -> list[Any]:
    """The arguments of ``api.setup_vehicle_update`` after the vehicle id, before the reason."""
    return [company, registration, fleet, joined_on, investment]


def _scoped(operator_conn: Conn, owner_conn: Conn, slot: int, *grants: str, **scope: Any) -> Member:
    who = provision_member(operator_conn, slot, "Revenue clerk", "Sam", f"Scoped{slot}")
    for grant in grants:
        set_override(owner_conn, who, grant)
    set_scope(owner_conn, who, who.org, **scope)
    return who


# --- list ------------------------------------------------------------------------------


def test_the_list_carries_targets_scheduled_items_and_away_periods_for_a_manager(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    kda = _vehicle(owner_conn, yard)
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET initial_investment = 2500000 WHERE id = %s", (kda,)
    )
    add_target(owner_conn, org, kda, 2, date(2026, 3, 1), 9000)
    add_target_set(owner_conn, org, kda, date(2026, 3, 10), [1300] * 6 + [Decimal("1300.50")])
    add_away(owner_conn, org, kda, date(2026, 2, 10), date(2026, 2, 12))
    add_away(owner_conn, org, kda, date(2026, 1, 5), date(2026, 1, 6))
    later = _vehicle(owner_conn, yard, "KDB 111A", joined_on=date(2026, 3, 10), company=yard.south)
    add_schedule(owner_conn, org, Version(date(2026, 1, 1), {kda: 100, later: 100}))
    add_schedule(owner_conn, org, Version(date(2026, 1, 1), {kda: 100}, end_on=date(2026, 3, 4)))
    add_schedule(owner_conn, org, Version(date(2026, 1, 1), {kda: 100}), stopped_from=TODAY)
    add_schedule(
        owner_conn, org, Version(date(2026, 1, 1), {kda: 50}), stopped_from=date(2026, 3, 6)
    )
    add_schedule(
        owner_conn,
        org,
        Version(date(2026, 1, 1), {kda: 100}),
        Version(date(2026, 2, 1), {later: 100}),
    )
    page = read(app_conn, "setup_vehicle_list", yard.owner, 1, 25, None)
    assert page["total"] == 2
    first, second = page["items"]
    assert first == {
        "id": str(kda),
        "company_id": str(yard.north),
        "company_name": "North Star",
        "registration": "KDA 482M",
        "fleet_number": "482M",
        "initial_investment": 2500000,
        "joined_on": "2026-01-01",
        "left_on": None,
        "active": True,
        "weekly_target": 9000.00,
        "day_targets": [1285.71] * 6 + [1285.74],
        "next_target": {
            "starts_on": "2026-03-10",
            "day_targets": [1300] * 6 + [1300.50],
            "weekly_target": 9100.50,
        },
        "targets": [
            {"effective_from": "2026-01-01", "weekly_amount": 7000.00, "revision": 1},
            {"effective_from": "2026-03-01", "weekly_amount": 9000.00, "revision": 2},
        ],
        "recurring_items": 2,
        "away": [
            {"left_on": "2026-01-05", "returned_on": "2026-01-06"},
            {"left_on": "2026-02-10", "returned_on": "2026-02-12"},
        ],
    }
    assert (second["registration"], second["active"], second["weekly_target"]) == (
        "KDB 111A",
        False,
        0,
    )
    assert (second["day_targets"], second["next_target"]["starts_on"]) == (None, "2026-03-10")
    assert second["recurring_items"] == 0


def test_the_set_in_force_shows_while_the_vehicle_is_away_but_no_weekly_target_counts(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    add_away(owner_conn, yard.owner.org, kda, date(2026, 3, 1), date(2026, 3, 9))
    (row,) = read(app_conn, "setup_vehicle_list", yard.owner, 1, 25, None)["items"]
    assert (row["active"], row["weekly_target"], row["next_target"]) == (True, 0, None)
    assert row["day_targets"] == [1000] * 7


def test_an_investment_viewer_gets_no_targets_and_no_scheduled_item_count(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    _vehicle(owner_conn, yard, "KDC 200B", company=yard.south)
    viewer = _scoped(operator_conn, owner_conn, 3, "reports.investment", companies=[yard.north])
    page = read(app_conn, "setup_vehicle_list", viewer, 1, 25, None)
    assert page["total"] == 1
    (row,) = page["items"]
    assert (row["id"], row["fleet_number"]) == (str(kda), "482M")
    assert (row["weekly_target"], row["targets"], row["recurring_items"]) == (None, [], None)
    assert (row["day_targets"], row["next_target"]) == (None, None)


def test_the_list_needs_vehicles_view_or_reports_investment_before_the_page_is_checked(
    app_conn: Conn, yard: Yard
) -> None:
    refuses(
        app_conn, "setup_vehicle_list", yard.clerk, [0, 25, None], "XC403", "permission_missing"
    )
    refuses(app_conn, "setup_vehicle_list", yard.owner, [0, 25, None], "XC422", "page_out_of_range")
    refuses(
        app_conn, "setup_vehicle_list", yard.owner, [1, 101, None], "XC422", "page_out_of_range"
    )


def test_the_list_is_by_registration_and_pages(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    for registration in ("KDC 300C", "KDA 100A", "KDB 200B"):
        _vehicle(owner_conn, yard, registration)
    page = read(app_conn, "setup_vehicle_list", yard.owner, 2, 2, None)
    assert page["total"] == 3
    assert [v["registration"] for v in page["items"]] == ["KDC 300C"]


def test_the_company_filter_counts_and_pages_its_matches_only(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    for registration in ("KFA 103F", "KFA 101F", "KFA 102F"):
        _vehicle(owner_conn, yard, registration)
    _vehicle(owner_conn, yard, "KFA 100F", company=yard.south)
    first = read(app_conn, "setup_vehicle_list", yard.owner, 1, 2, yard.north)
    assert (first["total"], [v["registration"] for v in first["items"]]) == (
        3,
        ["KFA 101F", "KFA 102F"],
    )
    second = read(app_conn, "setup_vehicle_list", yard.owner, 2, 2, yard.north)
    assert [v["registration"] for v in second["items"]] == ["KFA 103F"]
    assert read(app_conn, "setup_vehicle_list", yard.owner, 1, 25, None)["total"] == 4
    assert read(app_conn, "setup_vehicle_list", yard.owner, 1, 25, UUID(int=7)) == {
        "total": 0,
        "items": [],
    }
    viewer = _scoped(operator_conn, owner_conn, 3, "reports.investment", companies=[yard.north])
    assert read(app_conn, "setup_vehicle_list", viewer, 1, 25, yard.south) == {
        "total": 0,
        "items": [],
    }


def test_company_options_are_visible_companies_in_use_by_name(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    add_company(owner_conn, org, "Archived", archived_on=TODAY)
    later = add_company(owner_conn, org, "Archiving later", archived_on=date(2026, 3, 6))
    options = read(app_conn, "setup_company_options", yard.owner)
    assert options == [
        {"id": str(later), "name": "Archiving later"},
        {"id": str(yard.north), "name": "North Star"},
        {"id": str(yard.south), "name": "South Line"},
    ]
    for right in ("vehicles.add", "vehicles.edit"):
        scoped = _scoped(operator_conn, owner_conn, 3, right, companies=[yard.south])
        assert read(app_conn, "setup_company_options", scoped) == [
            {"id": str(yard.south), "name": "South Line"}
        ]
        set_override(owner_conn, scoped, right, False)
    viewer = _scoped(operator_conn, owner_conn, 4, "vehicles.view", "vehicles.target")
    for who in (yard.clerk, viewer):
        refuses(app_conn, "setup_company_options", who, [], "XC403", "permission_missing")


# --- create ---------------------------------------------------------------------------


def test_create_adds_the_vehicle_with_its_first_target_set_from_the_join_date_and_says_so(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    result = run(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        *_save(yard.north, " kda482m ", date(2026, 1, 1), fleet=" n-1 ", investment=2500000),
        None,
    )
    vehicle = UUID(str(result["id"]))
    assert result["outcome"] == "created"
    row = _row(owner_conn, org, vehicle)
    assert (row["registration"], row["company_id"], row["joined_on"], row["left_on"]) == (
        "KDA 482M",
        yard.north,
        date(2026, 1, 1),
        None,
    )
    assert (row["fleet_number"], row["initial_investment"]) == ("n-1", Decimal("2500000.00"))
    assert _targets(owner_conn, vehicle) == [(date(2026, 1, 1), WEEK)]
    creator = owner_conn.execute(
        "SELECT created_by FROM setup.vehicle_target_sets WHERE vehicle_id = %s", (vehicle,)
    ).fetchone()
    assert creator == {"created_by": yard.owner.id}
    (log,) = change_rows(owner_conn, org, "vehicles")
    assert (log["entity_id"], log["vehicle_id"]) == (vehicle, vehicle)
    assert log["reason"] == (
        "Added vehicle KDA 482M, fleet number n-1, to North Star with a weekly target of "
        "KES 7,000 from 2026-01-01"
    )
    assert log["before"] == "null"
    assert log["after"] == (
        f'{{"Id":"{vehicle}","Registration":"KDA 482M","FleetNumber":"n-1",'
        f'"CompanyId":"{yard.north}","JoinedOn":"2026-01-01","LeftOn":null,'
        '"InitialInvestment":2500000,"TargetSets":[{"StartsOn":"2026-01-01","Monday":1000,'
        '"Tuesday":1000,"Wednesday":1000,"Thursday":1000,"Friday":1000,"Saturday":1500,'
        '"Sunday":500}],"Away":[]}'
    )


def test_an_initial_investment_is_optional_and_zero_means_none(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    for registration, fleet, investment in [("KDA 482M", "N-1", None), ("KDB 111A", "N-2", 0)]:
        result = run(
            app_conn,
            "setup_vehicle_create",
            yard.owner,
            *_save(yard.north, registration, TODAY, fleet=fleet, investment=investment),
            None,
        )
        row = _row(owner_conn, yard.owner.org, UUID(str(result["id"])))
        assert row["initial_investment"] is None
    for investment in (-1, Decimal("1.005")):
        refuses(
            app_conn,
            "setup_vehicle_create",
            yard.owner,
            [*_save(yard.north, "KDC 200B", TODAY, fleet="N-3", investment=investment), None],
            "XC422",
            "money_invalid",
        )


def test_a_fractional_target_and_the_organization_currency_are_named(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_localization(owner_conn, yard.owner.org, currency="USD")
    run(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        *_save(
            yard.north, "KDA 482M", date(2026, 1, 1), [*WEEK[:5], Decimal("1650.5"), Decimal(500)]
        ),
        "Bought at auction.",
    )
    assert reasons(owner_conn, yard.owner.org, "vehicles") == [
        "Added vehicle KDA 482M, fleet number N-1, to North Star with a weekly target of "
        "USD 7,150.50 from 2026-01-01. Reason: Bought at auction."
    ]


def test_create_refuses_a_long_reason(app_conn: Conn, yard: Yard) -> None:
    refuses(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        [*_save(yard.north, "KDA 482M", TODAY), "x" * 501],
        "XC422",
        "reason_length",
    )


def test_create_refuses_a_registration_of_the_wrong_shape(app_conn: Conn, yard: Yard) -> None:
    refuses(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        [*_save(yard.north, "KDA-482M", TODAY), None],
        "XC422",
        "vehicle_registration_format",
    )


@pytest.mark.parametrize(
    ("days", "code"),
    [
        (None, "target_days_required"),
        (WEEK[:6], "target_days_required"),
        ([*WEEK, Decimal(1)], "target_days_required"),
        ([*WEEK[:6], None], "target_days_required"),
        ([*WEEK[:6], Decimal(0)], "money_invalid"),
        ([Decimal(-5), *WEEK[1:]], "money_invalid"),
        ([*WEEK[:3], Decimal("1.005"), *WEEK[4:]], "money_invalid"),
        ([*WEEK[:3], Decimal("1000000000000"), *WEEK[4:]], "money_invalid"),
    ],
)
def test_create_needs_seven_day_targets_that_are_money(
    app_conn: Conn, yard: Yard, days: Any, code: str
) -> None:
    refuses(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        [*_save(yard.north, "KDA 482M", TODAY, days), None],
        "XC422",
        code,
    )


@pytest.mark.parametrize(
    ("fleet", "code"),
    [
        (None, "vehicle_fleet_required"),
        ("  ", "vehicle_fleet_required"),
        ("F" * 21, "vehicle_fleet_length"),
    ],
)
def test_create_needs_a_fleet_number_of_at_most_twenty_characters(
    app_conn: Conn, yard: Yard, fleet: str | None, code: str
) -> None:
    refuses(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        [*_save(yard.north, "KDA 482M", TODAY, fleet=fleet), None],
        "XC422",
        code,
    )


def test_a_fleet_number_is_unique_in_its_company_whatever_the_case(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    _vehicle(owner_conn, yard, "KDA 482M", fleet_number="NS-07")
    error = refuses(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        [*_save(yard.north, "KDB 111A", TODAY, fleet=" ns-07 "), None],
        "XC422",
        "vehicle_fleet_taken",
    )
    assert json.loads(error.diag.message_detail or "") == {"fleet": "ns-07"}
    other = run(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        *_save(yard.south, "KDB 111A", TODAY, fleet="NS-07"),
        None,
    )
    assert other["outcome"] == "created"


def test_a_retired_vehicle_keeps_its_fleet_number_in_its_company(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    _vehicle(owner_conn, yard, "KDA 482M", fleet_number="NS-07", left_on=date(2026, 2, 1))
    error = refuses(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        [*_save(yard.north, "KDB 111A", TODAY, fleet="NS-07"), None],
        "XC422",
        "vehicle_fleet_taken",
    )
    assert json.loads(error.diag.message_detail or "") == {"fleet": "NS-07"}


@pytest.mark.parametrize("joined_on", [None, date(2026, 3, 6)])
def test_create_refuses_a_join_date_after_the_business_date(
    app_conn: Conn, yard: Yard, joined_on: date | None
) -> None:
    refuses(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        [*_save(yard.north, "KDA 482M", joined_on), None],
        "XC422",
        "vehicle_joined_future",
    )


def test_create_refuses_an_unknown_or_invisible_company(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    refuses(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        [*_save(UUID(int=3), "KDA 482M", TODAY), None],
        "XC404",
        "not_found",
    )
    scoped = _scoped(operator_conn, owner_conn, 3, "vehicles.add", companies=[yard.north])
    refuses(
        app_conn,
        "setup_vehicle_create",
        scoped,
        [*_save(yard.south, "KDA 482M", TODAY), None],
        "XC404",
        "not_found",
    )


def test_create_refuses_an_archived_company(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    owner_conn.execute(
        "UPDATE setup.psv_companies SET archived_on = %s WHERE id = %s", (TODAY, yard.south)
    )
    refuses(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        [*_save(yard.south, "KDA 482M", TODAY), None],
        "XC422",
        "vehicle_company_inactive",
    )


def test_a_vehicle_scope_cannot_create_a_vehicle(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    scoped = _scoped(operator_conn, owner_conn, 3, "vehicles.add", vehicles=[kda])
    refuses(
        app_conn,
        "setup_vehicle_create",
        scoped,
        [*_save(yard.north, "KDB 111A", TODAY), None],
        "XC403",
        "permission_missing",
    )
    company_scoped = _scoped(operator_conn, owner_conn, 4, "vehicles.add", companies=[yard.north])
    assert (
        run(
            app_conn,
            "setup_vehicle_create",
            company_scoped,
            *_save(yard.north, "KDB 111A", TODAY),
            None,
        )["outcome"]
        == "created"
    )


def test_create_refuses_a_registration_that_exists(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    _vehicle(owner_conn, yard, company=yard.south)
    refuses(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        [*_save(yard.north, "kda 482 m", TODAY), None],
        "XC422",
        "vehicle_registration_taken",
    )


def test_create_needs_vehicles_add(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    editor = _scoped(
        operator_conn,
        owner_conn,
        3,
        "vehicles.view",
        "vehicles.edit",
        "vehicles.target",
        all_companies=True,
    )
    for who in (yard.clerk, editor):
        refuses(
            app_conn,
            "setup_vehicle_create",
            who,
            [*_save(yard.north, "KDA 482M", TODAY), None],
            "XC403",
            "permission_missing",
        )
    other = seed_organization(owner_conn)
    refused(
        app_conn,
        "setup_vehicle_create",
        [
            other.user,
            yard.owner.org,
            REQUEST,
            *_save(yard.north, "KDA 482M", TODAY),
            None,
            T0,
        ],
        "XC403",
        "not_member",
    )


# --- update ---------------------------------------------------------------------------


def _update(
    app_conn: Conn,
    yard: Yard,
    vehicle: UUID,
    company: UUID,
    joined: date,
    fleet: str | None = "482M",
    investment: Any = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return run(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        vehicle,
        *_edit(company, "KDA 482M", joined, fleet, investment),
        reason,
    )


def test_a_new_fleet_number_is_saved_and_said_and_the_targets_stay(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard, target=15000)
    before = settings_version(owner_conn, yard.owner.org)
    result = _update(app_conn, yard, kda, yard.north, date(2026, 1, 1), " ns-9 ")
    assert (result["outcome"], result["version"]) == ("updated", before + 1)
    assert _row(owner_conn, yard.owner.org, kda)["fleet_number"] == "ns-9"
    assert _targets(owner_conn, kda) == [
        (date(2026, 1, 1), [Decimal("2142.86")] * 6 + [Decimal("2142.84")])
    ]
    (log,) = change_rows(owner_conn, yard.owner.org, "vehicles")
    assert log["reason"] == "Changed the fleet number of KDA 482M to ns-9"
    assert json.loads(log["before"])["FleetNumber"] == "482M"
    assert json.loads(log["after"])["TargetSets"] == json.loads(log["before"])["TargetSets"]


def test_the_initial_investment_is_changed_or_cleared_and_said(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    _update(app_conn, yard, kda, yard.north, date(2026, 1, 1), investment=Decimal("2500000.5"))
    assert _row(owner_conn, yard.owner.org, kda)["initial_investment"] == Decimal("2500000.50")
    unchanged = _update(
        app_conn, yard, kda, yard.north, date(2026, 1, 1), investment=Decimal("2500000.5")
    )
    assert unchanged["outcome"] == "unchanged"
    _update(app_conn, yard, kda, yard.north, date(2026, 1, 1), investment=0)
    assert _row(owner_conn, yard.owner.org, kda)["initial_investment"] is None
    assert _update(app_conn, yard, kda, yard.north, date(2026, 1, 1))["outcome"] == "unchanged"
    assert reasons(owner_conn, yard.owner.org, "vehicles") == [
        "Changed the initial investment of KDA 482M to KES 2,500,000.50",
        "Cleared the initial investment of KDA 482M",
    ]


def test_an_update_refuses_a_fleet_number_another_vehicle_of_the_company_uses(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    _vehicle(owner_conn, yard, "KDB 111A", fleet_number="NS-07")
    _vehicle(owner_conn, yard, "KDC 200B", company=yard.south, fleet_number="SL-01")
    error = refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [kda, *_edit(yard.north, "KDA 482M", date(2026, 1, 1), "ns-07"), None],
        "XC422",
        "vehicle_fleet_taken",
    )
    assert json.loads(error.diag.message_detail or "") == {"fleet": "ns-07"}
    refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [kda, *_edit(yard.south, "KDA 482M", date(2026, 1, 1), "SL-01"), None],
        "XC422",
        "vehicle_fleet_taken",
    )
    moved = _update(app_conn, yard, kda, yard.south, date(2026, 1, 1), "NS-07")
    assert moved["outcome"] == "updated"


def test_moving_company_and_join_date_says_both(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    _update(app_conn, yard, kda, yard.south, date(2026, 1, 5))
    row = _row(owner_conn, yard.owner.org, kda)
    assert (row["company_id"], row["joined_on"]) == (yard.south, date(2026, 1, 5))
    assert reasons(owner_conn, yard.owner.org, "vehicles") == [
        "Moved KDA 482M to South Line; changed when KDA 482M joined the fleet to 2026-01-05"
    ]
    assert len(_targets(owner_conn, kda)) == 1


def test_moving_the_join_date_before_the_first_set_copies_the_first_set_to_it(
    app_conn: Conn, owner_conn: Conn, executor: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    kda = _vehicle(owner_conn, yard, joined_on=date(2026, 2, 23))
    add_target(owner_conn, org, kda, 2, date(2026, 2, 28), 9000)
    _update(app_conn, yard, kda, yard.north, date(2026, 2, 13))
    seven, nine = [Decimal(1000)] * 7, [Decimal("1285.71")] * 6 + [Decimal("1285.74")]
    assert _targets(owner_conn, kda) == [
        (date(2026, 2, 13), seven),
        (date(2026, 2, 23), seven),
        (date(2026, 2, 28), nine),
    ]
    copied = owner_conn.execute(
        "SELECT created_by FROM setup.vehicle_target_sets WHERE vehicle_id = %s AND starts_on = %s",
        (kda, date(2026, 2, 13)),
    ).fetchone()
    assert copied == {"created_by": yard.owner.id}
    with executor.transaction():
        executor.execute(
            "SELECT tenancy.enter_organization(%s, %s, 'req', NULL)", (yard.owner.id, org)
        )
        for day, amount in [(date(2026, 2, 13), 7000), (date(2026, 2, 26), 7000), (TODAY, 9000)]:
            row = executor.execute("SELECT setup.target_on(%s, %s) AS t", (kda, day)).fetchone()
            assert row is not None and row["t"] == amount, day
    assert reasons(owner_conn, org, "vehicles") == [
        "Changed when KDA 482M joined the fleet to 2026-02-13"
    ]


def test_an_earlier_join_date_copies_nothing_when_a_set_already_covers_it(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    kda = _vehicle(owner_conn, yard, joined_on=date(2026, 2, 23))
    add_target(owner_conn, org, kda, 2, date(2026, 2, 1), 9000)
    _update(app_conn, yard, kda, yard.north, date(2026, 2, 13))
    assert [starts for starts, _ in _targets(owner_conn, kda)] == [
        date(2026, 2, 1),
        date(2026, 2, 23),
    ]
    _update(app_conn, yard, kda, yard.north, date(2026, 2, 20))
    assert len(_targets(owner_conn, kda)) == 2


def test_an_update_that_changes_nothing_is_unchanged_and_logs_nothing(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    version = settings_version(owner_conn, yard.owner.org)
    result = _update(app_conn, yard, kda, yard.north, date(2026, 1, 1), " 482M ")
    assert (result["outcome"], result["version"]) == ("unchanged", version)
    assert change_rows(owner_conn, yard.owner.org, "vehicles") == []


def test_update_refuses_a_retired_vehicle_and_a_new_registration(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [kda, *_edit(yard.north, "KDB 111A", date(2026, 1, 1)), None],
        "XC422",
        "vehicle_registration_change",
    )
    owner_conn.execute("UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s", (TODAY, kda))
    refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [kda, *_edit(yard.north, "KDA 482M", date(2026, 1, 1)), None],
        "XC422",
        "vehicle_retired_edit",
    )


def test_update_refuses_a_join_date_after_the_first_recorded_day(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    add_record(owner_conn, yard.owner.org, kda, date(2026, 1, 3), 1500, recorder=yard.owner.id)
    add_record(owner_conn, yard.owner.org, kda, date(2026, 1, 9), 1500, recorder=yard.owner.id)
    error = refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [kda, *_edit(yard.north, "KDA 482M", date(2026, 1, 4)), None],
        "XC422",
        "vehicle_join_after_revenue",
    )
    assert json.loads(error.diag.message_detail or "") == {
        "registration": "KDA 482M",
        "date": "2026-01-03",
    }
    assert _update(app_conn, yard, kda, yard.north, date(2026, 1, 3))["outcome"] == "updated"


def test_a_day_recorded_before_the_join_date_blocks_only_a_later_join_date(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard, joined_on=date(2026, 1, 5))
    add_record(owner_conn, yard.owner.org, kda, date(2026, 1, 3), 1500, recorder=yard.owner.id)
    assert _update(app_conn, yard, kda, yard.north, date(2026, 1, 5), "N-5")["outcome"] == "updated"
    refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [kda, *_edit(yard.north, "KDA 482M", date(2026, 1, 6)), None],
        "XC422",
        "vehicle_join_after_revenue",
    )


def test_update_checks_in_order(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    hidden = _vehicle(owner_conn, yard, "KDC 200B", company=yard.south)
    args = [kda, *_edit(yard.north, "KDA 482M", date(2026, 1, 1))]
    refuses(
        app_conn, "setup_vehicle_update", yard.owner, [*args, "x" * 501], "XC422", "reason_length"
    )
    refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [UUID(int=1), *_edit(UUID(int=2), "KDA-482M", TODAY, "", -1), None],
        "XC422",
        "vehicle_registration_format",
    )
    for fleet, code in [(None, "vehicle_fleet_required"), ("F" * 21, "vehicle_fleet_length")]:
        refuses(
            app_conn,
            "setup_vehicle_update",
            yard.owner,
            [UUID(int=1), *_edit(UUID(int=2), "KDA 482M", TODAY, fleet, -1), None],
            "XC422",
            code,
        )
    refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [UUID(int=1), *_edit(UUID(int=2), "KDA 482M", date(2026, 3, 6), "N-1", -1), None],
        "XC422",
        "money_invalid",
    )
    refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [UUID(int=1), *_edit(UUID(int=2), "KDA 482M", date(2026, 3, 6)), None],
        "XC422",
        "vehicle_joined_future",
    )
    refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [kda, *_edit(UUID(int=2), "KDA 482M", TODAY), None],
        "XC404",
        "not_found",
    )
    owner_conn.execute(
        "UPDATE setup.psv_companies SET archived_on = %s WHERE id = %s", (TODAY, yard.south)
    )
    refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [UUID(int=1), *_edit(yard.south, "KDA 482M", TODAY), None],
        "XC422",
        "vehicle_company_inactive",
    )
    refuses(
        app_conn,
        "setup_vehicle_update",
        yard.owner,
        [UUID(int=1), *_edit(yard.north, "KDA 482M", TODAY), None],
        "XC404",
        "not_found",
    )
    scoped = _scoped(operator_conn, owner_conn, 3, "vehicles.edit", companies=[yard.north])
    refuses(
        app_conn,
        "setup_vehicle_update",
        scoped,
        [hidden, *_edit(yard.north, "KDC 200B", TODAY, "200B"), None],
        "XC404",
        "not_found",
    )
    adder = _scoped(
        operator_conn, owner_conn, 4, "vehicles.add", "vehicles.target", all_companies=True
    )
    refuses(app_conn, "setup_vehicle_update", adder, [*args, None], "XC403", "permission_missing")


# --- retire ---------------------------------------------------------------------------


def test_retire_takes_the_vehicle_out_from_the_leave_date(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    result = run(app_conn, "setup_vehicle_retire", yard.owner, kda, TODAY, "Sold to the SACCO.")
    assert result["outcome"] == "updated"
    assert _row(owner_conn, yard.owner.org, kda)["left_on"] == TODAY
    assert reasons(owner_conn, yard.owner.org, "vehicles") == [
        "Vehicle KDA 482M left the fleet on 2026-03-05. Reason: Sold to the SACCO."
    ]
    again = run(app_conn, "setup_vehicle_retire", yard.owner, kda, TODAY, None)
    assert again["outcome"] == "unchanged"
    refuses(
        app_conn,
        "setup_vehicle_retire",
        yard.owner,
        [kda, date(2026, 3, 4), None],
        "XC422",
        "vehicle_already_retired",
    )


def test_retire_refuses_a_leave_date_on_or_before_a_recorded_day(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    for day in (date(2026, 3, 1), date(2026, 3, 3)):
        add_record(owner_conn, yard.owner.org, kda, day, 1500, recorder=yard.owner.id)
    error = refuses(
        app_conn,
        "setup_vehicle_retire",
        yard.owner,
        [kda, date(2026, 3, 1), None],
        "XC422",
        "vehicle_leave_before_revenue",
    )
    assert json.loads(error.diag.message_detail or "") == {
        "registration": "KDA 482M",
        "date": "2026-03-03",
    }
    assert (
        run(app_conn, "setup_vehicle_retire", yard.owner, kda, date(2026, 3, 4), None)["outcome"]
        == "updated"
    )


@pytest.mark.parametrize("left_on", [None, date(2026, 3, 6), date(2025, 12, 31)])
def test_retire_refuses_a_leave_date_outside_join_and_business_date(
    app_conn: Conn, owner_conn: Conn, yard: Yard, left_on: date | None
) -> None:
    kda = _vehicle(owner_conn, yard)
    refuses(
        app_conn,
        "setup_vehicle_retire",
        yard.owner,
        [kda, left_on, None],
        "XC422",
        "vehicle_leave_date_range",
    )


def test_a_second_leave_cannot_overlap_the_time_away(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    add_away(owner_conn, yard.owner.org, kda, date(2026, 2, 1), date(2026, 2, 20))
    refuses(
        app_conn,
        "setup_vehicle_retire",
        yard.owner,
        [kda, date(2026, 2, 19), None],
        "XC422",
        "vehicle_leave_before_return",
    )
    assert (
        run(app_conn, "setup_vehicle_retire", yard.owner, kda, date(2026, 2, 20), None)["outcome"]
        == "updated"
    )


def test_retire_refuses_an_unknown_or_invisible_vehicle(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    hidden = _vehicle(owner_conn, yard, "KDC 200B", company=yard.south)
    refuses(
        app_conn,
        "setup_vehicle_retire",
        yard.owner,
        [UUID(int=1), TODAY, None],
        "XC404",
        "not_found",
    )
    scoped = _scoped(operator_conn, owner_conn, 3, "vehicles.edit", companies=[yard.north])
    refuses(app_conn, "setup_vehicle_retire", scoped, [hidden, TODAY, None], "XC404", "not_found")
    refuses(
        app_conn,
        "setup_vehicle_retire",
        yard.owner,
        [hidden, TODAY, "x" * 501],
        "XC422",
        "reason_length",
    )


# --- restore --------------------------------------------------------------------------


def test_restoring_records_the_days_away_and_names_them(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    run(app_conn, "setup_vehicle_retire", yard.owner, kda, date(2026, 2, 28), None)
    result = run(app_conn, "setup_vehicle_restore", yard.owner, kda, None, None)
    assert result["outcome"] == "updated"
    assert _row(owner_conn, yard.owner.org, kda)["left_on"] is None
    assert _away(owner_conn, kda) == [(date(2026, 2, 28), TODAY)]
    log = change_rows(owner_conn, yard.owner.org, "vehicles")[-1]
    assert log["reason"] == (
        "Vehicle KDA 482M returned to the fleet on 2026-03-05; it was away from 2026-02-28 to "
        "2026-03-04"
    )
    assert json.loads(log["after"])["Away"] == [
        {"LeftOn": "2026-02-28", "ReturnedOn": "2026-03-05"}
    ]


def test_a_return_on_the_leave_date_records_no_time_away(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    run(app_conn, "setup_vehicle_retire", yard.owner, kda, TODAY, None)
    run(app_conn, "setup_vehicle_restore", yard.owner, kda, TODAY, "Back.")
    assert _away(owner_conn, kda) == []
    assert reasons(owner_conn, yard.owner.org, "vehicles")[-1] == (
        "Vehicle KDA 482M returned to the fleet on 2026-03-05. Reason: Back."
    )


def test_restoring_a_vehicle_in_the_fleet_is_unchanged(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    result = run(app_conn, "setup_vehicle_restore", yard.owner, kda, date(2020, 1, 1), None)
    assert result["outcome"] == "unchanged"
    assert change_rows(owner_conn, yard.owner.org, "vehicles") == []


@pytest.mark.parametrize("returned_on", [date(2026, 2, 27), date(2026, 3, 6)])
def test_restore_refuses_a_return_outside_the_time_away(
    app_conn: Conn, owner_conn: Conn, yard: Yard, returned_on: date
) -> None:
    kda = _vehicle(owner_conn, yard, left_on=date(2026, 2, 28))
    refuses(
        app_conn,
        "setup_vehicle_restore",
        yard.owner,
        [kda, returned_on, None],
        "XC422",
        "vehicle_return_date_range",
    )


def test_restore_needs_the_company_in_use_and_the_vehicle_in_reach(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    kdc = _vehicle(owner_conn, yard, "KDC 200B", company=yard.south, left_on=date(2026, 2, 28))
    owner_conn.execute(
        "UPDATE setup.psv_companies SET archived_on = %s WHERE id = %s",
        (date(2026, 3, 1), yard.south),
    )
    refuses(
        app_conn,
        "setup_vehicle_restore",
        yard.owner,
        [kdc, None, None],
        "XC422",
        "vehicle_company_archived_restore",
    )
    scoped = _scoped(operator_conn, owner_conn, 3, "vehicles.edit", companies=[yard.north])
    refuses(app_conn, "setup_vehicle_restore", scoped, [kdc, None, None], "XC404", "not_found")
    refuses(
        app_conn,
        "setup_vehicle_restore",
        yard.owner,
        [kdc, None, "x" * 501],
        "XC422",
        "reason_length",
    )


# --- report ---------------------------------------------------------------------------

MARCH_POSTINGS = [
    ("2026-03-01", "Crew lunch", 1, 50, 2),
    ("2026-03-01", "Tyres", 1, 100, 1),
    ("2026-03-02", "Crew lunch", 1, 50, 2),
    ("2026-03-02", "Parking", 1, 300, 2),
    ("2026-03-03", "Crew lunch", 1, 50, 2),
    ("2026-03-04", "Crew lunch", 1, 50, 2),
    ("2026-03-05", "Crew lunch", 1, 50, 2),
    ("2026-03-06", "Owner savings", 2, 1000, None),
    ("2026-03-08", "Tyres", 1, 100, 1),
    ("2026-03-09", "Parking", 1, 300, 2),
    ("2026-03-10", "Service", 1, 2000, 1),
    ("2026-03-13", "Owner savings", 2, 1000, None),
    ("2026-03-15", "Insurance", 1, 6000, 2),
    ("2026-03-15", "Tyres", 1, 100, 1),
    ("2026-03-16", "Parking", 1, 300, 2),
    ("2026-03-20", "Owner savings", 2, 1000, None),
    ("2026-03-22", "Tyres", 1, 100, 1),
    ("2026-03-25", "Service", 1, 2500, 1),
    ("2026-03-27", "Owner savings", 2, 1000, None),
    ("2026-03-29", "Tyres", 1, 100, 1),
    ("2026-03-31", "Loan repayment", 1, 10000, 3),
]


@pytest.fixture
def report(owner_conn: Conn, yard: Yard) -> Any:
    set_organization(owner_conn, yard.owner.org, business_date=date(2026, 3, 31))
    return seed_report_fleet(owner_conn, yard.owner.org, yard.owner.id)


def _report(
    app_conn: Conn,
    who: Member,
    vehicle: UUID,
    period: str | None,
    first: date | None,
    last: date | None,
) -> Any:
    return read(app_conn, "setup_vehicle_report", who, vehicle, period, first, last)


def test_the_report_counts_money_in_the_target_each_bucket_and_savings_once(
    app_conn: Conn, owner_conn: Conn, yard: Yard, report: Any
) -> None:
    march = _report(app_conn, yard.owner, report.kda, None, date(2026, 3, 1), date(2026, 3, 31))
    figures = {k: v for k, v in march.items() if k != "postings"}
    assert figures == {
        "vehicle_id": str(report.kda),
        "from_date": "2026-03-01",
        "through": "2026-03-31",
        "money_in": 43500,
        "target": 45000,
        "repairs": 5000,
        "charges": 7150,
        "loans": 10000,
        "money_out": 22150,
        "net": 21350,
        "savings": 4000,
        "after_savings": 17350,
        "costs": 22150,
    }
    items = {item: name for name, item in report.items.items()}
    assert [
        (p["day"], p["name"], p["kind"], p["amount"], p["bucket"]) for p in march["postings"]
    ] == MARCH_POSTINGS
    assert all(items[UUID(p["item_id"])] == p["name"] for p in march["postings"])
    assert all(p["source"] is None for p in march["postings"])
    add_record(
        owner_conn, yard.owner.org, report.kda, date(2026, 3, 31), 2000, recorder=yard.owner.id
    )
    month = _report(app_conn, yard.owner, report.kda, "month", None, None)
    assert (month["from_date"], month["through"]) == ("2026-03-01", "2026-03-31")
    assert (month["money_in"], month["target"], month["net"]) == (45500, 47000, 23350)


def test_a_vehicle_that_left_posts_nothing_from_its_leave_date(
    app_conn: Conn, owner_conn: Conn, yard: Yard, report: Any
) -> None:
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s",
        (date(2026, 3, 20), report.kda),
    )
    march = _report(app_conn, yard.owner, report.kda, None, date(2026, 3, 1), date(2026, 3, 31))
    assert (march["money_in"], march["target"]) == (19 * 1500, 15 * 1000 + 4 * 2000)
    assert max(p["day"] for p in march["postings"]) == "2026-03-16"
    february = _report(app_conn, yard.owner, report.kda, None, date(2026, 2, 1), date(2026, 2, 28))
    assert (february["money_in"], february["target"]) == (0, 28000)
    assert (february["repairs"], february["charges"], february["loans"], february["net"]) == (
        2000,
        1200,
        10000,
        -13200,
    )


def test_the_window_starts_at_the_join_date(app_conn: Conn, yard: Yard, report: Any) -> None:
    january = _report(app_conn, yard.owner, report.kda, None, date(2026, 1, 1), date(2026, 2, 3))
    assert (january["from_date"], january["through"]) == ("2026-01-01", "2026-02-03")
    assert (january["target"], january["postings"][0]["day"]) == (3000, "2026-02-02")


@pytest.mark.parametrize(
    ("first_day", "start"), [(1, "2026-09-21"), (0, "2026-09-20"), (6, "2026-09-26")]
)
def test_a_week_runs_from_the_organizations_first_day_through_today(
    app_conn: Conn, owner_conn: Conn, yard: Yard, first_day: int, start: str
) -> None:
    kda = _vehicle(owner_conn, yard)
    set_organization(owner_conn, yard.owner.org, business_date=date(2026, 9, 26))
    set_localization(owner_conn, yard.owner.org, first_day_of_week=first_day)
    week = _report(app_conn, yard.owner, kda, "week", None, None)
    assert (week["from_date"], week["through"]) == (start, "2026-09-26")
    month = _report(app_conn, yard.owner, kda, "month", date(2020, 1, 1), None)
    assert (month["from_date"], month["through"]) == ("2026-09-01", "2026-09-26")


def test_the_report_refuses_a_bad_period_or_range(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    for period, first, last, code in [
        ("day", None, None, "report_period_invalid"),
        ("Week", None, None, "report_period_invalid"),
        (None, date(2026, 3, 1), None, "report_range_required"),
        (None, None, None, "report_range_required"),
        (None, date(2026, 3, 2), date(2026, 3, 1), "report_range_invalid"),
        (None, date(2025, 3, 3), date(2026, 3, 5), "report_range_invalid"),
        (None, date(2026, 3, 1), date(2026, 3, 6), "report_range_invalid"),
    ]:
        refuses(
            app_conn, "setup_vehicle_report", yard.owner, [kda, period, first, last], "XC422", code
        )
    span = _report(app_conn, yard.owner, kda, None, date(2025, 3, 4), TODAY)
    assert span["from_date"] == "2025-03-04"


def test_a_report_outside_the_scope_is_not_found(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard)
    kdc = _vehicle(owner_conn, yard, "KDC 200B", company=yard.south)
    scoped = _scoped(operator_conn, owner_conn, 3, "vehicles.view", companies=[yard.north])
    assert _report(app_conn, scoped, kda, "month", None, None)["money_in"] == 0
    for vehicle in (kdc, UUID(int=1)):
        refuses(
            app_conn,
            "setup_vehicle_report",
            scoped,
            [vehicle, "month", None, None],
            "XC404",
            "not_found",
        )
    refuses(
        app_conn,
        "setup_vehicle_report",
        yard.clerk,
        [kda, "month", None, None],
        "XC403",
        "permission_missing",
    )
