"""The company routines (``api.setup_company_*``), called as ``xcode_app``: one test per
``Raises:`` code, the ``unchanged`` no-ops, the list (order, vehicle counts, scope), the
automatic reasons and snapshots byte for byte, and tenant isolation.

Vehicles are inserted as ``xcode_owner`` where a test needs one older than the business date or
one that has not joined yet; every result is read back as ``xcode_owner``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pytest

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn
from ..support.setup_rows import change_rows, read, reasons, refuses, run
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

TODAY = date(2026, 3, 5)


@dataclass(frozen=True, slots=True)
class Office:
    owner: Member
    clerk: Member


@pytest.fixture
def office(operator_conn: Conn, owner_conn: Conn) -> Office:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 2, "Revenue clerk", "Cleo", "Clerk")
    set_organization(owner_conn, owner.org, business_date=TODAY)
    return Office(owner, clerk)


def _company(owner_conn: Conn, org: UUID, company: UUID) -> dict[str, Any]:
    row = owner_conn.execute(
        "SELECT * FROM setup.psv_companies WHERE organization_id = %s AND id = %s", (org, company)
    ).fetchone()
    assert row is not None
    return row


def _scoped(operator_conn: Conn, owner_conn: Conn, slot: int, **scope: Any) -> Member:
    return _holding(
        operator_conn,
        owner_conn,
        slot,
        "companies.view",
        "companies.add",
        "companies.edit",
        **scope,
    )


def _holding(
    operator_conn: Conn, owner_conn: Conn, slot: int, *rights: str, **scope: Any
) -> Member:
    who = provision_member(operator_conn, slot, "Fleet manager", "Sam", f"Scoped{slot}")
    for right in rights:
        set_override(owner_conn, who, right)
    set_scope(owner_conn, who, who.org, **(scope or {"all_companies": True}))
    return who


# --- list ------------------------------------------------------------------------------


def test_the_list_is_by_name_with_visible_vehicles_in_the_fleet_today(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    org = office.owner.org
    south = add_company(owner_conn, org, "South Line", archived_on=date(2026, 3, 1))
    north = add_company(owner_conn, org, "North Star")
    later = add_company(owner_conn, org, "Mid Way", archived_on=date(2026, 3, 9))
    add_vehicle(owner_conn, org, north, "KDA 482M")
    add_vehicle(owner_conn, org, north, "KDB 111A", joined_on=date(2026, 3, 10))
    add_vehicle(owner_conn, org, north, "KDC 200B", left_on=TODAY)
    add_vehicle(owner_conn, org, north, "KDD 300C", left_on=date(2026, 3, 6))
    page = read(app_conn, "setup_company_list", office.owner, 1, 25)
    assert page["total"] == 3
    assert page["items"] == [
        {
            "id": str(later),
            "name": "Mid Way",
            "vehicle_count": 0,
            "active": True,
            "archived_on": "2026-03-09",
        },
        {
            "id": str(north),
            "name": "North Star",
            "vehicle_count": 2,
            "active": True,
            "archived_on": None,
        },
        {
            "id": str(south),
            "name": "South Line",
            "vehicle_count": 0,
            "active": False,
            "archived_on": "2026-03-01",
        },
    ]


def test_the_list_pages_after_ordering(app_conn: Conn, owner_conn: Conn, office: Office) -> None:
    for name in ("Charlie", "Alpha", "Bravo"):
        add_company(owner_conn, office.owner.org, name)
    page = read(app_conn, "setup_company_list", office.owner, 2, 1)
    assert page["total"] == 3
    assert [c["name"] for c in page["items"]] == ["Bravo"]


def test_a_scoped_list_shows_its_companies_and_those_owning_its_vehicles(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, office: Office
) -> None:
    org = office.owner.org
    north = add_company(owner_conn, org, "North Star")
    south = add_company(owner_conn, org, "South Line")
    add_company(owner_conn, org, "West End")
    add_vehicle(owner_conn, org, north, "KDA 482M")
    add_vehicle(owner_conn, org, north, "KDB 111A")
    kdc = add_vehicle(owner_conn, org, south, "KDC 200B")
    add_vehicle(owner_conn, org, south, "KDD 300C")
    who = _scoped(operator_conn, owner_conn, 3, companies=[north], vehicles=[kdc])
    page = read(app_conn, "setup_company_list", who, 1, 25)
    assert page["total"] == 2
    assert [(c["name"], c["vehicle_count"]) for c in page["items"]] == [
        ("North Star", 2),
        ("South Line", 1),
    ]


@pytest.mark.parametrize(("page", "size"), [(0, 25), (1, 0), (1, 101), (100001, 1)])
def test_the_list_refuses_a_page_out_of_range(
    app_conn: Conn, office: Office, page: int, size: int
) -> None:
    refuses(
        app_conn, "setup_company_list", office.owner, [page, size], "XC422", "page_out_of_range"
    )


def test_the_list_needs_companies_view(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, office: Office
) -> None:
    fleet = _holding(operator_conn, owner_conn, 3, "vehicles.view", "vehicles.add")
    for who in (office.clerk, fleet):
        refuses(app_conn, "setup_company_list", who, [1, 25], "XC403", "permission_missing")
    for slot, right in [(4, "companies.view"), (5, "companies.add")]:
        holder = _holding(operator_conn, owner_conn, slot, right)
        assert read(app_conn, "setup_company_list", holder, 1, 25)["total"] == 0


# --- create ---------------------------------------------------------------------------


def test_create_adds_the_company_and_logs_it(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    org = office.owner.org
    before = settings_version(owner_conn, org)
    result = run(app_conn, "setup_company_create", office.owner, "  North Star ", None)
    company = UUID(str(result["id"]))
    assert result["outcome"] == "created"
    assert result["version"] == before + 1 == settings_version(owner_conn, org)
    assert _company(owner_conn, org, company)["name"] == "North Star"
    (row,) = change_rows(owner_conn, org, "companies")
    assert (row["entity_id"], row["vehicle_id"], row["version"]) == (company, None, before + 1)
    assert row["reason"] == "Added company North Star"
    assert row["before"] == "null"
    assert row["after"] == (
        f'{{"Id":"{company}","Name":"North Star","ArchivedOn":null,"Active":true}}'
    )
    assert row["request_id"] == REQUEST
    (audit,) = audit_events(owner_conn, org, "setup.companies")
    assert audit["entity"] == str(company)
    assert audit["after"] == json.loads(row["after"])


def test_a_typed_reason_follows_the_automatic_one(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    run(app_conn, "setup_company_create", office.owner, "North Star", "Signed with the SACCO")
    assert reasons(owner_conn, office.owner.org, "companies") == [
        "Added company North Star. Reason: Signed with the SACCO."
    ]


def test_create_refuses_a_reason_over_500_characters(app_conn: Conn, office: Office) -> None:
    refuses(
        app_conn,
        "setup_company_create",
        office.owner,
        ["North", "x" * 501],
        "XC422",
        "reason_length",
    )


@pytest.mark.parametrize("name", [None, "", "   ", "x" * 161])
def test_create_refuses_a_name_outside_1_to_160(
    app_conn: Conn, office: Office, name: str | None
) -> None:
    refuses(
        app_conn,
        "setup_company_create",
        office.owner,
        [name, None],
        "XC422",
        "company_name_length",
    )


def test_create_needs_an_actor_who_sees_every_company(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, office: Office
) -> None:
    north = add_company(owner_conn, office.owner.org, "North Star")
    who = _scoped(operator_conn, owner_conn, 3, companies=[north])
    refuses(app_conn, "setup_company_create", who, ["South", None], "XC403", "permission_missing")


def test_create_refuses_a_name_another_company_has_ignoring_case(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    add_company(owner_conn, office.owner.org, "North Star")
    refuses(
        app_conn,
        "setup_company_create",
        office.owner,
        ["NORTH star", None],
        "XC422",
        "company_name_taken",
    )


def test_create_needs_companies_add(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, office: Office
) -> None:
    editor = _holding(operator_conn, owner_conn, 3, "companies.view", "companies.edit")
    for who in (office.clerk, editor):
        refuses(
            app_conn,
            "setup_company_create",
            who,
            ["North", None],
            "XC403",
            "permission_missing",
        )
    adder = _holding(operator_conn, owner_conn, 4, "companies.add")
    assert run(app_conn, "setup_company_create", adder, "North", None)["outcome"] == "created"


def test_another_organization_cannot_act_here(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    other = seed_organization(owner_conn)
    args = [other.user, office.owner.org, REQUEST, "North", None, T0]
    refused(app_conn, "setup_company_create", args, "XC403", "not_member")
    company = add_company(owner_conn, office.owner.org, "North Star")
    refused(
        app_conn,
        "setup_company_rename",
        [other.user, other.org, REQUEST, company, "Elsewhere", None, T0],
        "XC404",
        "not_found",
    )
    refused(
        app_conn,
        "setup_company_list",
        [other.user, office.owner.org, REQUEST, 1, 25, T0],
        "XC403",
        "not_member",
    )


# --- rename ---------------------------------------------------------------------------


def test_rename_changes_the_name_and_says_so(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    org = office.owner.org
    company = add_company(owner_conn, org, "North Star")
    result = run(app_conn, "setup_company_rename", office.owner, company, "North Line", " ")
    assert (result["id"], result["outcome"]) == (company, "updated")
    (row,) = change_rows(owner_conn, org, "companies")
    assert row["reason"] == "Renamed company North Star to North Line"
    assert row["before"] == (
        f'{{"Id":"{company}","Name":"North Star","ArchivedOn":null,"Active":true}}'
    )
    assert row["after"] == (
        f'{{"Id":"{company}","Name":"North Line","ArchivedOn":null,"Active":true}}'
    )


def test_a_company_archived_after_the_business_date_snapshots_as_not_active(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    # The business date was moved back below the archive date: the company is still in use,
    # so it can be renamed, and its snapshot says what .NET's says (Active = no archive date).
    org = office.owner.org
    company = add_company(owner_conn, org, "North Star", archived_on=date(2026, 3, 10))
    result = run(app_conn, "setup_company_rename", office.owner, company, "North Line", None)
    assert result["outcome"] == "updated"
    (row,) = change_rows(owner_conn, org, "companies")
    assert row["after"] == (
        f'{{"Id":"{company}","Name":"North Line","ArchivedOn":"2026-03-10","Active":false}}'
    )


def test_renaming_to_the_same_name_is_unchanged_and_logs_nothing(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    org = office.owner.org
    company = add_company(owner_conn, org, "North Star")
    version = settings_version(owner_conn, org)
    result = run(app_conn, "setup_company_rename", office.owner, company, " North Star ", None)
    assert (result["outcome"], result["version"]) == ("unchanged", version)
    assert change_rows(owner_conn, org, "companies") == []
    assert settings_version(owner_conn, org) == version


def test_rename_may_change_only_the_case_of_its_own_name(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    company = add_company(owner_conn, office.owner.org, "North Star")
    result = run(app_conn, "setup_company_rename", office.owner, company, "NORTH STAR", None)
    assert result["outcome"] == "updated"


def test_rename_refuses_another_companys_name(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    company = add_company(owner_conn, office.owner.org, "North Star")
    add_company(owner_conn, office.owner.org, "South Line")
    refuses(
        app_conn,
        "setup_company_rename",
        office.owner,
        [company, "south line", None],
        "XC422",
        "company_name_taken",
    )


@pytest.mark.parametrize("archived_on", [TODAY, date(2026, 3, 1)])
def test_an_archived_company_cannot_be_renamed(
    app_conn: Conn, owner_conn: Conn, office: Office, archived_on: date
) -> None:
    company = add_company(owner_conn, office.owner.org, "North Star", archived_on=archived_on)
    refuses(
        app_conn,
        "setup_company_rename",
        office.owner,
        [company, "North Line", None],
        "XC422",
        "company_archived_rename",
    )


def test_a_company_archived_from_a_later_date_can_still_be_renamed(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    company = add_company(owner_conn, office.owner.org, "North", archived_on=date(2026, 3, 6))
    assert (
        run(app_conn, "setup_company_rename", office.owner, company, "North Line", None)["outcome"]
        == "updated"
    )


def test_rename_refuses_an_unknown_or_invisible_company(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, office: Office
) -> None:
    org = office.owner.org
    north = add_company(owner_conn, org, "North Star")
    south = add_company(owner_conn, org, "South Line")
    who = _scoped(operator_conn, owner_conn, 3, companies=[north])
    refuses(app_conn, "setup_company_rename", who, [south, "X", None], "XC404", "not_found")
    refuses(
        app_conn,
        "setup_company_rename",
        office.owner,
        [UUID(int=4), "X", None],
        "XC404",
        "not_found",
    )


def test_rename_checks_the_name_before_finding_the_company(app_conn: Conn, office: Office) -> None:
    refuses(
        app_conn,
        "setup_company_rename",
        office.owner,
        [UUID(int=4), "", None],
        "XC422",
        "company_name_length",
    )
    refuses(
        app_conn,
        "setup_company_rename",
        office.owner,
        [UUID(int=4), "X", "x" * 501],
        "XC422",
        "reason_length",
    )


# --- archive and restore --------------------------------------------------------------


def test_archive_and_restore_log_and_answer_unchanged_when_repeated(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    org = office.owner.org
    company = add_company(owner_conn, org, "North Line")
    add_vehicle(owner_conn, org, company, "KDA 482M", left_on=TODAY)
    assert run(app_conn, "setup_company_archive", office.owner, company, None)["outcome"] == (
        "updated"
    )
    assert _company(owner_conn, org, company)["archived_on"] == TODAY
    assert run(app_conn, "setup_company_archive", office.owner, company, None)["outcome"] == (
        "unchanged"
    )
    assert run(app_conn, "setup_company_restore", office.owner, company, None)["outcome"] == (
        "updated"
    )
    assert _company(owner_conn, org, company)["archived_on"] is None
    assert run(app_conn, "setup_company_restore", office.owner, company, None)["outcome"] == (
        "unchanged"
    )
    rows = change_rows(owner_conn, org, "companies")
    assert [r["reason"] for r in rows] == [
        "Archived company North Line",
        "Restored company North Line",
    ]
    assert rows[0]["after"] == (
        f'{{"Id":"{company}","Name":"North Line","ArchivedOn":"2026-03-05","Active":false}}'
    )
    assert rows[1]["after"] == (
        f'{{"Id":"{company}","Name":"North Line","ArchivedOn":null,"Active":true}}'
    )


@pytest.mark.parametrize(
    ("joined_on", "left_on"),
    [(date(2026, 1, 1), None), (date(2026, 1, 1), date(2026, 3, 6)), (date(2026, 3, 9), None)],
)
def test_archive_needs_every_vehicle_retired_first(
    app_conn: Conn,
    owner_conn: Conn,
    office: Office,
    joined_on: date,
    left_on: date | None,
) -> None:
    company = add_company(owner_conn, office.owner.org, "North Star")
    add_vehicle(
        owner_conn, office.owner.org, company, "KDA 482M", joined_on=joined_on, left_on=left_on
    )
    refuses(
        app_conn,
        "setup_company_archive",
        office.owner,
        [company, None],
        "XC422",
        "company_has_vehicles",
    )


def test_an_archive_on_another_date_is_refused_and_restore_cancels_a_later_one(
    app_conn: Conn, owner_conn: Conn, office: Office
) -> None:
    org = office.owner.org
    earlier = add_company(owner_conn, org, "Earlier", archived_on=date(2026, 3, 1))
    later = add_company(owner_conn, org, "Later", archived_on=date(2026, 3, 8))
    refuses(
        app_conn,
        "setup_company_archive",
        office.owner,
        [earlier, None],
        "XC422",
        "company_already_archived",
    )
    refuses(
        app_conn,
        "setup_company_archive",
        office.owner,
        [later, None],
        "XC422",
        "company_already_archived",
    )
    assert run(app_conn, "setup_company_restore", office.owner, later, "Cancelled")["outcome"] == (
        "updated"
    )
    assert _company(owner_conn, org, later)["archived_on"] is None
    assert reasons(owner_conn, org, "companies") == ["Restored company Later. Reason: Cancelled."]


def test_archive_and_restore_refuse_an_unknown_company_and_a_long_reason(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, office: Office
) -> None:
    adder = _holding(operator_conn, owner_conn, 3, "companies.view", "companies.add")
    for routine in ("setup_company_archive", "setup_company_restore"):
        refuses(app_conn, routine, office.owner, [UUID(int=4), None], "XC404", "not_found")
        refuses(app_conn, routine, office.owner, [UUID(int=4), "x" * 501], "XC422", "reason_length")
        for who in (office.clerk, adder):
            refuses(app_conn, routine, who, [UUID(int=4), None], "XC403", "permission_missing")
    refuses(
        app_conn,
        "setup_company_rename",
        adder,
        [UUID(int=4), "X", None],
        "XC403",
        "permission_missing",
    )
