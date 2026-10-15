"""The main category routines (``api.setup_expense_main_category_*``), called as ``xcode_app``:
the paged list by name with how many categories and items sit under each and how many
categories have none, a name unique ignoring case, the rename sentence and ``unchanged``, the
check order, and the rights (any of ``catalog.view``, ``expenses.view``, ``scheduled.view`` to
read; ``catalog.add`` to add; ``catalog.edit`` to rename). Moving categories between main
categories is in ``test_setup_expense_routines``; other organizations in
``test_setup_object_authorization``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

import pytest

from ..support.scenario import Conn
from ..support.setup_rows import (
    add_category,
    add_item,
    add_main_category,
    change_rows,
    read,
    reasons,
    refuses,
    run,
)
from ..support.tenancy import Member, provision_member, set_override, settings_version


@dataclass(frozen=True, slots=True)
class Catalogue:
    owner: Member
    clerk: Member
    repairs: UUID
    finance: UUID


@pytest.fixture
def catalogue(operator_conn: Conn, owner_conn: Conn) -> Catalogue:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 2, "Revenue clerk", "Cleo", "Clerk")
    org = owner.org
    repairs = add_main_category(owner_conn, org, "Repairs")
    finance = add_main_category(owner_conn, org, "Finance")
    garage = add_category(owner_conn, org, "Garage", bucket=None, main_category=repairs)
    tyres = add_category(owner_conn, org, "Tyres", bucket=None, main_category=repairs)
    add_category(owner_conn, org, "Fuel", bucket=None)
    add_category(owner_conn, org, "Parking", bucket=2)
    for category, item in [(garage, "Service"), (garage, "Towing"), (tyres, "Front pair")]:
        add_item(owner_conn, org, category, item)
    return Catalogue(owner=owner, clerk=clerk, repairs=repairs, finance=finance)


# --- list ------------------------------------------------------------------------------


def test_the_list_counts_categories_and_items_under_each_and_those_under_none(
    app_conn: Conn, catalogue: Catalogue
) -> None:
    page = read(app_conn, "setup_expense_main_category_list", catalogue.owner, 1, 25)
    assert page == {
        "total": 2,
        "items": [
            {"id": str(catalogue.finance), "name": "Finance", "category_count": 0, "item_count": 0},
            {"id": str(catalogue.repairs), "name": "Repairs", "category_count": 2, "item_count": 3},
        ],
        "categories_without_main": 2,
    }


def test_the_list_pages_by_name(app_conn: Conn, catalogue: Catalogue) -> None:
    second = read(app_conn, "setup_expense_main_category_list", catalogue.owner, 2, 1)
    assert (second["total"], [m["name"] for m in second["items"]]) == (2, ["Repairs"])
    assert read(app_conn, "setup_expense_main_category_list", catalogue.owner, 3, 1)["items"] == []
    for page, size in [(0, 25), (1, 101)]:
        refuses(
            app_conn,
            "setup_expense_main_category_list",
            catalogue.owner,
            [page, size],
            "XC422",
            "page_out_of_range",
        )


@pytest.mark.parametrize(
    ("grant", "can_read"),
    [
        (None, False),
        ("catalog.view", True),
        ("expenses.view", True),
        ("scheduled.view", True),
        ("savings.view", False),
        ("expenses.capture", True),
        ("pettycash.spend", False),
    ],
)
def test_reading_needs_catalogue_expense_or_schedule_access_before_the_page_is_checked(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue, grant: str | None, can_read: bool
) -> None:
    if grant is not None:
        set_override(owner_conn, catalogue.clerk, grant)
    if can_read:
        page = read(app_conn, "setup_expense_main_category_list", catalogue.clerk, 1, 25)
        assert page["total"] == 2
    else:
        refuses(
            app_conn,
            "setup_expense_main_category_list",
            catalogue.clerk,
            [0, 25],
            "XC403",
            "permission_missing",
        )


# --- create ----------------------------------------------------------------------------


def test_a_main_category_is_added_trimmed_and_logged(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    org = catalogue.owner.org
    before = settings_version(owner_conn, org)
    result = run(app_conn, "setup_expense_main_category_create", catalogue.owner, " Road costs ")
    main = UUID(str(result["id"]))
    assert (result["outcome"], result["version"]) == ("created", before + 1)
    stored = owner_conn.execute(
        "SELECT name FROM setup.expense_main_categories WHERE id = %s", (main,)
    ).fetchone()
    assert stored == {"name": "Road costs"}
    (log,) = change_rows(owner_conn, org, "expenses")
    assert (log["entity_id"], log["vehicle_id"], log["before"]) == (main, None, "null")
    assert log["reason"] == "Added main category Road costs"
    assert log["after"] == f'{{"Id":"{main}","Name":"Road costs"}}'


@pytest.mark.parametrize(
    ("name", "code"),
    [
        (None, "expense_name_length"),
        ("   ", "expense_name_length"),
        ("x" * 101, "expense_name_length"),
        (" REPAIRS ", "expense_main_taken"),
    ],
)
def test_a_main_category_needs_a_new_name_of_1_to_100_characters(
    app_conn: Conn, catalogue: Catalogue, name: str | None, code: str
) -> None:
    refuses(app_conn, "setup_expense_main_category_create", catalogue.owner, [name], "XC422", code)


def test_a_name_of_100_characters_is_accepted(app_conn: Conn, catalogue: Catalogue) -> None:
    result = run(app_conn, "setup_expense_main_category_create", catalogue.owner, "m" * 100)
    assert result["outcome"] == "created"


# --- rename ----------------------------------------------------------------------------


def test_a_rename_is_saved_and_said_and_the_same_name_is_unchanged(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    owner, repairs = catalogue.owner, catalogue.repairs
    result = run(app_conn, "setup_expense_main_category_rename", owner, repairs, " Garage costs ")
    assert (result["id"], result["outcome"]) == (repairs, "updated")
    version = settings_version(owner_conn, owner.org)
    again = run(app_conn, "setup_expense_main_category_rename", owner, repairs, "Garage costs")
    assert (again["outcome"], again["version"]) == ("unchanged", version)
    case = run(app_conn, "setup_expense_main_category_rename", owner, repairs, "Garage Costs")
    assert case["outcome"] == "updated"
    assert reasons(owner_conn, owner.org, "expenses") == [
        "Renamed main category Repairs to Garage costs",
        "Renamed main category Garage costs to Garage Costs",
    ]
    first = change_rows(owner_conn, owner.org, "expenses")[0]
    assert json.loads(first["before"]) == {"Id": str(repairs), "Name": "Repairs"}
    assert json.loads(first["after"]) == {"Id": str(repairs), "Name": "Garage costs"}


def test_a_rename_checks_the_name_then_the_record_then_uniqueness(
    app_conn: Conn, catalogue: Catalogue
) -> None:
    for args, sqlstate, code in [
        ([UUID(int=1), " "], "XC422", "expense_name_length"),
        ([UUID(int=1), "finance"], "XC404", "not_found"),
        ([catalogue.repairs, "FINANCE"], "XC422", "expense_main_taken"),
    ]:
        refuses(
            app_conn,
            "setup_expense_main_category_rename",
            catalogue.owner,
            args,
            sqlstate,
            code,
        )


def test_adding_needs_catalog_add_and_renaming_catalog_edit(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, catalogue: Catalogue
) -> None:
    for slot, held, routine, args in [
        (3, ("catalog.view", "catalog.edit", "catalog.stop"), "create", ["Road costs"]),
        (4, ("catalog.view", "catalog.add", "catalog.stop"), "rename", [catalogue.repairs, "X"]),
    ]:
        who = provision_member(operator_conn, slot, "Revenue clerk", "Sam", f"Rights{slot}")
        for right in held:
            set_override(owner_conn, who, right)
        refuses(
            app_conn,
            f"setup_expense_main_category_{routine}",
            who,
            args,
            "XC403",
            "permission_missing",
        )
    refuses(
        app_conn,
        "setup_expense_main_category_create",
        catalogue.clerk,
        ["Road costs"],
        "XC403",
        "permission_missing",
    )
