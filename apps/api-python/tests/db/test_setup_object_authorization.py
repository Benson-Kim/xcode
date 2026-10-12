"""Every setup routine that takes an id, called as ``xcode_app`` by the Owner of another
organization with the ids of this one: a write or a single read answers ``not_found`` (the
404 of the contract), a list or option read holds none of this organization's ids, a filter
naming this organization's company gives an empty page, an organization the caller does not
belong to is ``not_member``, and nothing of this organization changes."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest

from ..support.rows import OrganizationRows, seed_organization
from ..support.scenario import T0, Conn
from ..support.setup_rows import Definition, add_target_set, shares
from ..support.tenancy import (
    REQUEST,
    Member,
    add_company,
    add_vehicle,
    provision_member,
    refused,
    set_organization,
    set_override,
    set_scope,
    write,
)

SETUP_TABLES = [
    "psv_companies",
    "fleet_vehicles",
    "vehicle_target_sets",
    "vehicle_away_periods",
    "vehicle_investments",
    "expense_main_categories",
    "expense_categories",
    "expense_items",
    "recurring_items",
    "recurring_versions",
    "recurring_allocations",
]
START = date(2026, 10, 1)
WEEK = [Decimal(1000)] * 7


@pytest.fixture
def home(owner_conn: Conn) -> OrganizationRows:
    return seed_organization(owner_conn)


@pytest.fixture
def stranger(owner_conn: Conn) -> OrganizationRows:
    return seed_organization(owner_conn)


def _state(owner_conn: Conn, org: UUID) -> dict[str, Any]:
    state: dict[str, Any] = {
        table: owner_conn.execute(
            f"SELECT * FROM setup.{table} WHERE organization_id = %s ORDER BY id", (org,)
        ).fetchall()
        for table in SETUP_TABLES
    }
    state["change_log"] = owner_conn.execute(
        "SELECT count(*) AS n FROM tenancy.change_log WHERE organization_id = %s", (org,)
    ).fetchone()
    state["settings_version"] = owner_conn.execute(
        "SELECT settings_version FROM tenancy.organizations WHERE id = %s", (org,)
    ).fetchone()
    return state


def _calls(home: OrganizationRows, stranger: OrganizationRows) -> list[tuple[str, list[Any], str]]:
    to_home = Definition(allocations=shares((home.vehicle, 1000)), amount=1000, start=START)
    to_own = Definition(allocations=shares((stranger.vehicle, 1000)), amount=1000, start=START)
    home_item = Definition(
        allocations=shares((stranger.vehicle, 1000)),
        amount=1000,
        name=None,
        kind=1,
        expense_item_id=home.item,
        start=START,
    )
    joined = date(2026, 1, 5)
    return [
        ("setup_company_rename", [home.company, "Elsewhere", None], "not_found"),
        ("setup_company_archive", [home.company, None], "not_found"),
        ("setup_company_restore", [home.company, None], "not_found"),
        (
            "setup_vehicle_create",
            [home.company, "KDC 300C", "S-9", START, WEEK, None, None],
            "not_found",
        ),
        (
            "setup_vehicle_update",
            [home.vehicle, stranger.company, "KDA 482M", "MT-01", joined, None, None],
            "not_found",
        ),
        (
            "setup_vehicle_update",
            [stranger.vehicle, home.company, "KDA 482M", "MT-01", joined, None, None],
            "not_found",
        ),
        ("setup_target_set_list", [home.vehicle], "not_found"),
        ("setup_target_set_save", [home.vehicle, START, WEEK], "not_found"),
        # The set started long ago: the 404 comes before the started-set refusal.
        ("setup_target_set_remove", [home.target_set], "not_found"),
        ("setup_vehicle_retire", [home.vehicle, START, None], "not_found"),
        ("setup_vehicle_restore", [home.vehicle, None, None], "not_found"),
        ("setup_vehicle_report", [home.vehicle, "month", None, None], "not_found"),
        ("setup_expense_main_category_rename", [home.main_category, "Elsewhere"], "not_found"),
        ("setup_expense_category_create", ["Fuel", home.main_category], "not_found"),
        ("setup_expense_category_update", [home.category, "Cover", None, False], "not_found"),
        (
            "setup_expense_category_update",
            [stranger.category, "Cover", home.main_category, True],
            "not_found",
        ),
        ("setup_expense_category_set_stopped", [home.category, True], "not_found"),
        ("setup_expense_item_create", [home.category, "Third party"], "not_found"),
        ("setup_expense_item_rename", [home.item, "Third party"], "not_found"),
        ("setup_expense_item_set_stopped", [home.item, True], "not_found"),
        ("setup_recurring_create", to_home.args(), "not_found"),
        # A cost naming this organization's expense item finds no item in use.
        ("setup_recurring_create", home_item.args(), "recurring_item_not_in_use"),
        ("setup_recurring_revise", [home.recurring, *to_own.args()], "not_found"),
        ("setup_recurring_stop", [home.recurring, True, "Ended"], "not_found"),
        ("setup_recurring_cancel_stop", [home.recurring], "not_found"),
        ("setup_investment_get", [home.vehicle], "not_found"),
        ("setup_investment_create", [home.vehicle, START, "Deposit", 100], "not_found"),
        ("setup_investment_update", [home.investment, START, "Deposit", 100], "not_found"),
        ("setup_investment_delete", [home.investment], "not_found"),
    ]


def _answer(conn: Conn, routine: str, who: OrganizationRows, args: list[Any]) -> str:
    placeholders = ", ".join(["%s"] * (len(args) + 4))
    try:
        conn.execute(
            f"SELECT * FROM api.{routine}({placeholders})",
            (who.user, who.org, REQUEST, *args, T0),
        ).fetchall()
    except psycopg.Error as error:
        return str(error.diag.message_primary)
    return "answered"


def test_another_organizations_ids_are_not_found_and_nothing_changes(
    app_conn: Conn, owner_conn: Conn, home: OrganizationRows, stranger: OrganizationRows
) -> None:
    before = _state(owner_conn, home.org)
    calls = _calls(home, stranger)
    answers = [(routine, _answer(app_conn, routine, stranger, args)) for routine, args, _ in calls]
    assert answers == [(routine, code) for routine, _, code in calls]
    assert _state(owner_conn, home.org) == before


READS: list[tuple[str, list[Any], str]] = [
    ("setup_company_list", [1, 100], "company"),
    ("setup_company_options", [], "company"),
    ("setup_vehicle_list", [1, 100, None], "vehicle"),
    ("setup_vehicle_options", [], "vehicle"),
    ("setup_recurring_list", [1, 100, None, None, None], "recurring"),
    ("setup_expense_category_list", [1, 100], "category"),
    ("setup_expense_main_category_list", [1, 100], "main_category"),
    ("setup_expense_item_options", [], "item"),
]


def _read(conn: Conn, routine: str, who: OrganizationRows, args: list[Any]) -> Any:
    placeholders = ", ".join(["%s"] * (len(args) + 4))
    row = conn.execute(
        f"SELECT api.{routine}({placeholders}) AS r", (who.user, who.org, REQUEST, *args, T0)
    ).fetchone()
    assert row is not None
    return row["r"]


@pytest.mark.parametrize(("routine", "args", "own"), READS)
def test_lists_and_options_hold_none_of_another_organizations_ids(
    app_conn: Conn,
    home: OrganizationRows,
    stranger: OrganizationRows,
    routine: str,
    args: list[Any],
    own: str,
) -> None:
    text = json.dumps(_read(app_conn, routine, stranger, args))
    assert str(getattr(stranger, own)) in text
    for value in (
        home.company,
        home.vehicle,
        home.vehicle2,
        home.category,
        home.item,
        home.recurring,
        home.version,
        home.target_set,
        home.main_category,
    ):
        assert str(value) not in text


def test_a_filter_naming_another_organizations_company_gives_an_empty_page(
    app_conn: Conn, home: OrganizationRows, stranger: OrganizationRows
) -> None:
    vehicles = _read(app_conn, "setup_vehicle_list", stranger, [1, 100, home.company])
    recurring = _read(
        app_conn, "setup_recurring_list", stranger, [1, 100, None, home.company, None]
    )
    assert (vehicles["total"], vehicles["items"]) == (0, [])
    assert (recurring["total"], recurring["items"]) == (0, [])


@pytest.mark.parametrize(
    ("routine", "args"),
    [
        ("setup_company_list", [1, 25]),
        ("setup_company_create", ["North", None]),
        ("setup_vehicle_list", [1, 25, None]),
        ("setup_recurring_list", [1, 25, None, None, None]),
        ("setup_expense_category_create", ["Fuel", None]),
        ("setup_investment_get", [None]),
        ("setup_vehicle_options", []),
        ("setup_target_set_list", [None]),
        ("setup_target_set_save", [None, START, WEEK]),
        ("setup_target_set_remove", [None]),
        ("setup_expense_main_category_list", [1, 25]),
        ("setup_expense_main_category_create", ["Fuel"]),
        ("setup_expense_main_category_rename", [None, "Fuel"]),
    ],
)
def test_naming_an_organization_the_caller_does_not_belong_to_is_not_member(
    app_conn: Conn,
    home: OrganizationRows,
    stranger: OrganizationRows,
    routine: str,
    args: list[Any],
) -> None:
    refused(app_conn, routine, [stranger.user, home.org, REQUEST, *args, T0], "XC403", "not_member")


# --- the same organization, outside the caller's data scope ---------------------------

TODAY = date(2026, 3, 5)


@pytest.fixture
def owner(operator_conn: Conn, owner_conn: Conn) -> Member:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    set_organization(owner_conn, owner.org, business_date=TODAY)
    return owner


def _scoped(operator_conn: Conn, owner_conn: Conn, *grants: str, **scope: Any) -> Member:
    who = provision_member(operator_conn, 3, "Fleet manager", "Sam", "Scoped")
    for grant in grants:
        set_override(owner_conn, who, grant)
    set_scope(owner_conn, who, who.org, **scope)
    return who


def _archived_on(owner_conn: Conn, company: UUID) -> date | None:
    row = owner_conn.execute(
        "SELECT archived_on FROM setup.psv_companies WHERE id = %s", (company,)
    ).fetchone()
    assert row is not None
    return row["archived_on"]


def test_a_company_outside_the_scope_cannot_be_archived_or_restored(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, owner: Member
) -> None:
    north = add_company(owner_conn, owner.org, "North Star")
    west = add_company(owner_conn, owner.org, "West Way")
    south = add_company(owner_conn, owner.org, "South Line", archived_on=date(2026, 3, 1))
    who = _scoped(operator_conn, owner_conn, "companies.view", "companies.edit", companies=[north])
    for routine, company in (("setup_company_archive", west), ("setup_company_restore", south)):
        refused(
            app_conn, routine, [who.id, who.org, REQUEST, company, None, T0], "XC404", "not_found"
        )
    assert (_archived_on(owner_conn, west), _archived_on(owner_conn, south)) == (
        None,
        date(2026, 3, 1),
    )


def test_an_item_sharing_only_to_hidden_vehicles_is_not_found_rather_than_refused(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, owner: Member
) -> None:
    north = add_company(owner_conn, owner.org, "North Star")
    south = add_company(owner_conn, owner.org, "South Line")
    add_vehicle(owner_conn, owner.org, north, "KDA 482M")
    kdc = add_vehicle(owner_conn, owner.org, south, "KDC 200B")
    saving = Definition(allocations=shares((kdc, 1000)), amount=1000, start=TODAY)
    item = write(
        app_conn, "setup_recurring_create", owner.id, owner.org, REQUEST, *saving.args(), T0
    )
    who = _scoped(
        operator_conn,
        owner_conn,
        "scheduled.view",
        "scheduled.edit",
        "savings.view",
        "savings.edit",
        companies=[north],
    )
    for routine, args in (
        ("setup_recurring_stop", [item["id"], True, "Ended"]),
        ("setup_recurring_cancel_stop", [item["id"]]),
    ):
        refused(app_conn, routine, [who.id, who.org, REQUEST, *args, T0], "XC404", "not_found")


def test_target_sets_of_a_vehicle_outside_the_scope_are_not_found(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, owner: Member
) -> None:
    north = add_company(owner_conn, owner.org, "North Star")
    south = add_company(owner_conn, owner.org, "South Line")
    kda = add_vehicle(owner_conn, owner.org, north, "KDA 482M")
    kdc = add_vehicle(owner_conn, owner.org, south, "KDC 200B")
    later = add_target_set(owner_conn, owner.org, kdc, date(2026, 3, 20), WEEK)
    who = _scoped(operator_conn, owner_conn, "vehicles.view", "vehicles.target", companies=[north])
    for routine, args in (
        ("setup_target_set_list", [kdc]),
        ("setup_target_set_save", [kdc, date(2026, 3, 10), WEEK]),
        ("setup_target_set_remove", [later]),
    ):
        refused(app_conn, routine, [who.id, who.org, REQUEST, *args, T0], "XC404", "not_found")
    saved = write(
        app_conn,
        "setup_target_set_save",
        who.id,
        who.org,
        REQUEST,
        kda,
        date(2026, 3, 10),
        WEEK,
        T0,
    )
    assert saved["outcome"] == "created"
    remaining = owner_conn.execute(
        "SELECT count(*) AS n FROM setup.vehicle_target_sets WHERE vehicle_id = %s", (kdc,)
    ).fetchone()
    assert remaining == {"n": 1}
