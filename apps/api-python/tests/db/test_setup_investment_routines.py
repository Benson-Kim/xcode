"""The investment routines (``api.setup_investment_*``), called as ``xcode_app``: one test per
``Raises:`` code, the ``unchanged`` update, the change log kept against the vehicle, the hard
delete whose log entry keeps what the entry held, ``returned`` as the vehicle report's net from
the join date, ``percent_paid_off`` (null, positive, negative, half away from zero), and the
scoped and foreign callers who cannot reach an entry.

The vehicles and their scheduled items are those of the report scenario, seeded as
``xcode_owner``, with the business date on 2026-03-31 unless a test moves it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn
from ..support.setup_rows import (
    ReportFleet,
    add_investment,
    add_record,
    change_rows,
    read,
    refuses,
    run,
    seed_report_fleet,
)
from ..support.tenancy import (
    REQUEST,
    Member,
    add_company,
    add_vehicle,
    audit_events,
    provision_member,
    refused,
    set_organization,
    set_override,
    set_scope,
    settings_version,
)

TODAY = date(2026, 3, 31)


@dataclass(frozen=True, slots=True)
class Fleet:
    owner: Member
    admin: Member
    clerk: Member
    report: ReportFleet
    south: UUID
    kdc: UUID


@pytest.fixture
def fleet(operator_conn: Conn, owner_conn: Conn) -> Fleet:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    admin = provision_member(operator_conn, 2, "Office admin", "Olive", "Admin")
    clerk = provision_member(operator_conn, 3, "Revenue clerk", "Cleo", "Clerk")
    set_scope(owner_conn, admin, admin.org, all_companies=True)
    set_organization(owner_conn, owner.org, business_date=TODAY)
    report = seed_report_fleet(owner_conn, owner.org, owner.id)
    south = add_company(owner_conn, owner.org, "South Line")
    kdc = add_vehicle(owner_conn, owner.org, south, "KDC 200B", joined_on=date(2026, 3, 1))
    return Fleet(owner, admin, clerk, report, south, kdc)


def _entry(owner_conn: Conn, fleet: Fleet, vehicle: UUID | None = None, **fields: Any) -> UUID:
    return add_investment(
        owner_conn,
        fleet.owner.org,
        vehicle or fleet.report.kda,
        fields.get("invested_on", date(2026, 2, 1)),
        fields.get("description", "Purchase"),
        fields.get("amount", 15000),
        recorder=fields.get("recorder", fleet.owner.id),
        recorded_at=fields.get("recorded_at", T0),
    )


def _stored(owner_conn: Conn, entry: UUID) -> dict[str, Any] | None:
    return owner_conn.execute(
        "SELECT * FROM setup.vehicle_investments WHERE id = %s", (entry,)
    ).fetchone()


def _get(app_conn: Conn, who: Member, vehicle: UUID) -> Any:
    return read(app_conn, "setup_investment_get", who, vehicle)


def _snapshot(entry: UUID, vehicle: UUID, day: str, description: str, amount: str) -> str:
    return (
        f'{{"Id":"{entry}","VehicleId":"{vehicle}","Date":"{day}",'
        f'"Description":"{description}","Amount":{amount}}}'
    )


def _scoped(operator_conn: Conn, owner_conn: Conn, slot: int, *grants: str, **scope: Any) -> Member:
    who = provision_member(operator_conn, slot, "Revenue clerk", "Sam", f"Scoped{slot}")
    for grant in grants:
        set_override(owner_conn, who, grant)
    set_scope(owner_conn, who, who.org, **scope)
    return who


# --- get -------------------------------------------------------------------------------


def test_get_lists_the_entries_by_date_then_instant_with_who_recorded_them(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    later = T0 + timedelta(hours=1)
    purchase = _entry(owner_conn, fleet, recorded_at=later)
    deposit = _entry(
        owner_conn, fleet, description="Deposit", amount=Decimal("3999.50"), recorder=fleet.admin.id
    )
    booking = _entry(
        owner_conn,
        fleet,
        invested_on=date(2026, 1, 15),
        description="Booking",
        amount=Decimal("1000.50"),
    )
    _entry(owner_conn, fleet, fleet.report.kdb, description="Other vehicle", amount=99)
    got = _get(app_conn, fleet.owner, fleet.report.kda)
    entries = got.pop("entries")
    assert got == {
        "vehicle_id": str(fleet.report.kda),
        "total_invested": 20000,
        "returned": 8150,
        "percent_paid_off": 41,
    }
    assert [
        (e["id"], e["invested_on"], e["description"], e["amount"], e["recorded_by"])
        for e in entries
    ] == [
        (str(booking), "2026-01-15", "Booking", Decimal("1000.50"), "Antony Maina"),
        (str(deposit), "2026-02-01", "Deposit", Decimal("3999.50"), "Olive Admin"),
        (str(purchase), "2026-02-01", "Purchase", 15000, "Antony Maina"),
    ]
    assert [datetime.fromisoformat(e["recorded_at"]) for e in entries] == [T0, T0, later]


def test_nothing_invested_has_no_percentage(app_conn: Conn, fleet: Fleet) -> None:
    got = _get(app_conn, fleet.owner, fleet.kdc)
    assert got == {
        "vehicle_id": str(fleet.kdc),
        "total_invested": 0,
        "returned": 0,
        "percent_paid_off": None,
        "entries": [],
    }


@pytest.mark.parametrize(
    ("today", "invested", "returned", "percent"),
    [
        (TODAY, 16300, 8150, 50),
        (TODAY, 20000, 8150, 41),
        (TODAY, 13040, 8150, 63),
        (date(2026, 2, 28), 26400, -13200, -50),
        (date(2026, 2, 28), 21120, -13200, -63),
    ],
)
def test_the_share_paid_off_rounds_half_away_from_zero(
    app_conn: Conn,
    owner_conn: Conn,
    fleet: Fleet,
    today: date,
    invested: int,
    returned: int,
    percent: int,
) -> None:
    set_organization(owner_conn, fleet.owner.org, business_date=today)
    _entry(owner_conn, fleet, amount=invested)
    got = _get(app_conn, fleet.owner, fleet.report.kda)
    assert (got["total_invested"], got["returned"], got["percent_paid_off"]) == (
        invested,
        returned,
        percent,
    )


def test_returned_is_the_reports_net_from_the_join_date_through_today(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    def net(vehicle: UUID, joined: date) -> Any:
        report = read(app_conn, "setup_vehicle_report", fleet.owner, vehicle, None, joined, TODAY)
        return report["net"]

    vehicles = [(fleet.report.kda, date(2026, 2, 1)), (fleet.report.kdb, date(2026, 2, 1))]
    for vehicle, joined in [*vehicles, (fleet.kdc, date(2026, 3, 1))]:
        assert _get(app_conn, fleet.owner, vehicle)["returned"] == net(vehicle, joined)
    add_record(owner_conn, fleet.owner.org, fleet.report.kda, TODAY, 2000, recorder=fleet.owner.id)
    assert _get(app_conn, fleet.owner, fleet.report.kda)["returned"] == 10150 == net(*vehicles[0])
    assert _get(app_conn, fleet.owner, fleet.report.kdb)["returned"] == -2500


def test_get_needs_reports_investment(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, fleet: Fleet
) -> None:
    editor = _scoped(
        operator_conn, owner_conn, 4, "vehicles.view", "vehicles.edit", all_companies=True
    )
    for who in (fleet.clerk, editor):
        refuses(
            app_conn,
            "setup_investment_get",
            who,
            [fleet.report.kda],
            "XC403",
            "permission_missing",
        )


def test_get_refuses_an_unknown_vehicle_and_one_outside_the_scope(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, fleet: Fleet
) -> None:
    refuses(app_conn, "setup_investment_get", fleet.owner, [UUID(int=1)], "XC404", "not_found")
    by_company = _scoped(
        operator_conn, owner_conn, 4, "reports.investment", companies=[fleet.report.company]
    )
    assert _get(app_conn, by_company, fleet.report.kda)["returned"] == 8150
    refuses(app_conn, "setup_investment_get", by_company, [fleet.kdc], "XC404", "not_found")
    by_vehicle = _scoped(
        operator_conn, owner_conn, 5, "reports.investment", vehicles=[fleet.report.kdb]
    )
    assert _get(app_conn, by_vehicle, fleet.report.kdb)["vehicle_id"] == str(fleet.report.kdb)
    refuses(app_conn, "setup_investment_get", by_vehicle, [fleet.report.kda], "XC404", "not_found")


# --- create ----------------------------------------------------------------------------


def test_create_records_the_entry_and_logs_it_against_the_vehicle(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org, kda = fleet.owner.org, fleet.report.kda
    before = settings_version(owner_conn, org)
    result = run(
        app_conn,
        "setup_investment_create",
        fleet.admin,
        kda,
        date(2026, 3, 10),
        "  New engine ",
        Decimal("12000.50"),
    )
    entry = UUID(str(result["id"]))
    assert result["outcome"] == "created"
    assert result["version"] == before + 1 == settings_version(owner_conn, org)
    stored = _stored(owner_conn, entry)
    assert stored is not None
    assert (
        stored["vehicle_id"],
        stored["invested_on"],
        stored["description"],
        stored["amount"],
    ) == (
        kda,
        date(2026, 3, 10),
        "New engine",
        Decimal("12000.50"),
    )
    assert (stored["recorded_by"], stored["recorded_at"]) == (fleet.admin.id, T0)
    (row,) = change_rows(owner_conn, org, "investment")
    assert (row["entity_id"], row["vehicle_id"], row["version"]) == (kda, kda, before + 1)
    assert row["reason"] == "Recorded investment New engine on KDA 482M"
    assert row["before"] == "null"
    assert row["after"] == _snapshot(entry, kda, "2026-03-10", "New engine", "12000.5")
    assert row["request_id"] == REQUEST
    (audit,) = audit_events(owner_conn, org, "setup.investment")
    assert audit["entity"] == str(kda)
    assert audit["after"] == json.loads(row["after"])
    assert _get(app_conn, fleet.admin, kda)["total_invested"] == Decimal("12000.50")


def test_an_entry_dated_today_or_before_the_join_date_is_accepted(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    for day in (TODAY, date(2025, 12, 1)):
        run(app_conn, "setup_investment_create", fleet.owner, fleet.report.kda, day, "Deposit", 100)
    assert len(change_rows(owner_conn, fleet.owner.org, "investment")) == 2


@pytest.mark.parametrize("day", [None, date(2026, 4, 1)])
def test_create_refuses_a_missing_or_future_date(
    app_conn: Conn, fleet: Fleet, day: date | None
) -> None:
    refuses(
        app_conn,
        "setup_investment_create",
        fleet.owner,
        [fleet.report.kda, day, "Deposit", 100],
        "XC422",
        "investment_date_invalid",
    )


@pytest.mark.parametrize("description", [None, "", "   ", "x" * 161])
def test_create_refuses_a_description_outside_one_to_160_characters(
    app_conn: Conn, fleet: Fleet, description: str | None
) -> None:
    refuses(
        app_conn,
        "setup_investment_create",
        fleet.owner,
        [fleet.report.kda, TODAY, description, 100],
        "XC422",
        "investment_description_length",
    )


def test_a_160_character_description_is_accepted(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    result = run(
        app_conn, "setup_investment_create", fleet.owner, fleet.report.kda, TODAY, "x" * 160, 1
    )
    stored = _stored(owner_conn, UUID(str(result["id"])))
    assert stored is not None and stored["description"] == "x" * 160


@pytest.mark.parametrize("amount", [None, 0, -5, Decimal("1.005"), Decimal("1000000000000")])
def test_create_refuses_an_amount_that_is_not_money(
    app_conn: Conn, fleet: Fleet, amount: Any
) -> None:
    refuses(
        app_conn,
        "setup_investment_create",
        fleet.owner,
        [fleet.report.kda, TODAY, "Deposit", amount],
        "XC422",
        "money_invalid",
    )


def test_create_checks_the_vehicle_then_the_date_then_the_description_then_the_amount(
    app_conn: Conn, fleet: Fleet
) -> None:
    kda = fleet.report.kda
    for args, code in [
        ([UUID(int=1), None, None, 0], "not_found"),
        ([kda, None, None, 0], "investment_date_invalid"),
        ([kda, TODAY, None, 0], "investment_description_length"),
        ([kda, TODAY, "Deposit", 0], "money_invalid"),
    ]:
        status = "XC404" if code == "not_found" else "XC422"
        refuses(app_conn, "setup_investment_create", fleet.owner, args, status, code)


def test_create_needs_vehicles_edit(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, fleet: Fleet
) -> None:
    viewer = _scoped(operator_conn, owner_conn, 4, "reports.investment", all_companies=True)
    for who in (fleet.clerk, viewer):
        refuses(
            app_conn,
            "setup_investment_create",
            who,
            [fleet.report.kda, TODAY, "Deposit", 100],
            "XC403",
            "permission_missing",
        )


# --- update ----------------------------------------------------------------------------


def test_update_changes_the_entry_and_logs_both_sides(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org, kda = fleet.owner.org, fleet.report.kda
    entry = _entry(owner_conn, fleet)
    before = settings_version(owner_conn, org)
    later = T0 + timedelta(days=1)
    result = run(
        app_conn,
        "setup_investment_update",
        fleet.admin,
        entry,
        date(2026, 2, 3),
        " Gearbox ",
        9000,
        now=later,
    )
    assert result == {"id": entry, "version": before + 1, "outcome": "updated"}
    stored = _stored(owner_conn, entry)
    assert stored is not None
    assert (stored["invested_on"], stored["description"], stored["amount"]) == (
        date(2026, 2, 3),
        "Gearbox",
        9000,
    )
    assert (stored["recorded_by"], stored["recorded_at"], stored["updated_at"]) == (
        fleet.owner.id,
        T0,
        later,
    )
    (row,) = change_rows(owner_conn, org, "investment")
    assert (row["entity_id"], row["vehicle_id"]) == (kda, kda)
    assert row["reason"] == "Changed investment Gearbox on KDA 482M"
    assert row["before"] == _snapshot(entry, kda, "2026-02-01", "Purchase", "15000")
    assert row["after"] == _snapshot(entry, kda, "2026-02-03", "Gearbox", "9000")


def test_an_update_that_changes_nothing_is_unchanged_and_logs_nothing(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org = fleet.owner.org
    entry = _entry(owner_conn, fleet)
    version = settings_version(owner_conn, org)
    result = run(
        app_conn,
        "setup_investment_update",
        fleet.owner,
        entry,
        date(2026, 2, 1),
        " Purchase  ",
        Decimal("15000.00"),
    )
    assert result == {"id": entry, "version": version, "outcome": "unchanged"}
    assert settings_version(owner_conn, org) == version
    assert change_rows(owner_conn, org, "investment") == []


def test_update_checks_the_entry_then_the_date_then_the_description_then_the_amount(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    entry = _entry(owner_conn, fleet)
    for args, status, code in [
        ([UUID(int=1), None, None, 0], "XC404", "not_found"),
        ([entry, None, None, 0], "XC422", "investment_date_invalid"),
        ([entry, date(2026, 4, 1), None, 0], "XC422", "investment_date_invalid"),
        ([entry, TODAY, "   ", 0], "XC422", "investment_description_length"),
        ([entry, TODAY, "x" * 161, 1], "XC422", "investment_description_length"),
        ([entry, TODAY, "Deposit", Decimal("0.001")], "XC422", "money_invalid"),
    ]:
        refuses(app_conn, "setup_investment_update", fleet.owner, args, status, code)
    refuses(
        app_conn,
        "setup_investment_update",
        fleet.clerk,
        [entry, TODAY, "Deposit", 1],
        "XC403",
        "permission_missing",
    )


# --- delete ----------------------------------------------------------------------------


def test_delete_removes_the_entry_and_the_log_keeps_what_it_held(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org, kda = fleet.owner.org, fleet.report.kda
    entry = _entry(owner_conn, fleet, amount=Decimal("15000.25"))
    kept = _entry(owner_conn, fleet, description="Deposit", amount=5000)
    before = settings_version(owner_conn, org)
    result = run(app_conn, "setup_investment_delete", fleet.admin, entry)
    assert result == {"id": entry, "version": before + 1, "outcome": "updated"}
    assert _stored(owner_conn, entry) is None
    assert _stored(owner_conn, kept) is not None
    (row,) = change_rows(owner_conn, org, "investment")
    assert (row["entity_id"], row["vehicle_id"]) == (kda, kda)
    assert row["reason"] == "Removed investment Purchase on KDA 482M"
    assert row["before"] == _snapshot(entry, kda, "2026-02-01", "Purchase", "15000.25")
    assert row["after"] == "null"
    (audit,) = audit_events(owner_conn, org, "setup.investment")
    assert audit["after"] is None
    got = _get(app_conn, fleet.owner, kda)
    assert [e["id"] for e in got["entries"]] == [str(kept)]
    assert got["total_invested"] == 5000
    refuses(app_conn, "setup_investment_delete", fleet.admin, [entry], "XC404", "not_found")


def test_delete_needs_vehicles_edit(app_conn: Conn, owner_conn: Conn, fleet: Fleet) -> None:
    entry = _entry(owner_conn, fleet)
    refuses(
        app_conn, "setup_investment_delete", fleet.clerk, [entry], "XC403", "permission_missing"
    )
    assert _stored(owner_conn, entry) is not None


# --- scope and tenancy -----------------------------------------------------------------


def test_a_scoped_manager_cannot_reach_an_entry_outside_the_scope(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, fleet: Fleet
) -> None:
    manager = _scoped(
        operator_conn,
        owner_conn,
        4,
        "reports.investment",
        "vehicles.edit",
        companies=[fleet.report.company],
    )
    outside = _entry(owner_conn, fleet, fleet.kdc)
    inside = _entry(owner_conn, fleet)
    for routine, args in [
        ("setup_investment_create", [fleet.kdc, TODAY, "Deposit", 100]),
        ("setup_investment_update", [outside, TODAY, "Deposit", 100]),
        ("setup_investment_delete", [outside]),
    ]:
        refuses(app_conn, routine, manager, args, "XC404", "not_found")
    assert (
        run(app_conn, "setup_investment_update", manager, inside, TODAY, "Deposit", 100)["outcome"]
        == "updated"
    )
    assert run(app_conn, "setup_investment_delete", manager, inside)["outcome"] == "updated"
    assert _stored(owner_conn, outside) is not None


def test_another_organization_cannot_reach_these_entries(
    app_conn: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    other = seed_organization(owner_conn)
    entry = _entry(owner_conn, fleet)
    refused(
        app_conn,
        "setup_investment_get",
        [other.user, fleet.owner.org, REQUEST, fleet.report.kda, T0],
        "XC403",
        "not_member",
    )
    for routine, args in [
        ("setup_investment_get", [fleet.report.kda]),
        ("setup_investment_create", [fleet.report.kda, TODAY, "Deposit", 100]),
        ("setup_investment_update", [entry, TODAY, "Deposit", 100]),
        ("setup_investment_delete", [entry]),
    ]:
        refused(
            app_conn, routine, [other.user, other.org, REQUEST, *args, T0], "XC404", "not_found"
        )
    assert _stored(owner_conn, entry) is not None
