"""The expense catalogue routines (``api.setup_expense_*``), called as ``xcode_app``: every
code, the rename and move reasons (a category under a main category or none), turning off and
on (a stop dated later is cancelled by turning on), a stopped category still accepting items,
the options leaving stopped items and categories out, the ordering by name then id, and the
right each read and write needs. The catalogue has no data scope; the main categories have
their own module, ``test_setup_main_category_routines``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pytest

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn
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
from ..support.tenancy import (
    REQUEST,
    Member,
    provision_member,
    refused,
    set_organization,
    set_override,
    settings_version,
)

TODAY = date(2026, 3, 5)


@dataclass(frozen=True, slots=True)
class Catalogue:
    owner: Member
    clerk: Member
    charges: UUID
    loans: UUID
    garage: UUID
    repairs: UUID
    parking: UUID
    insurance: UUID
    repayment: UUID
    tyres: UUID
    towing: UUID


@pytest.fixture
def catalogue(operator_conn: Conn, owner_conn: Conn) -> Catalogue:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 2, "Revenue clerk", "Cleo", "Clerk")
    set_organization(owner_conn, owner.org, business_date=TODAY)
    org = owner.org
    charges = add_category(owner_conn, org, "Charges", bucket=2)
    loans = add_category(owner_conn, org, "Loans", bucket=3)
    repairs = add_main_category(owner_conn, org, "Repairs")
    garage = add_category(owner_conn, org, "Garage and repairs", bucket=1, main_category=repairs)
    return Catalogue(
        owner=owner,
        clerk=clerk,
        charges=charges,
        loans=loans,
        garage=garage,
        repairs=repairs,
        parking=add_item(owner_conn, org, charges, "Parking"),
        insurance=add_item(owner_conn, org, charges, "Insurance"),
        repayment=add_item(owner_conn, org, loans, "Loan repayment"),
        tyres=add_item(owner_conn, org, garage, "Tyres"),
        towing=add_item(owner_conn, org, garage, "Towing"),
    )


def _category(owner_conn: Conn, category: UUID) -> dict[str, Any]:
    row = owner_conn.execute(
        "SELECT * FROM setup.expense_categories WHERE id = %s", (category,)
    ).fetchone()
    assert row is not None
    return row


def _item(owner_conn: Conn, item: UUID) -> dict[str, Any]:
    row = owner_conn.execute("SELECT * FROM setup.expense_items WHERE id = %s", (item,)).fetchone()
    assert row is not None
    return row


# --- list and options -----------------------------------------------------------------


def test_categories_are_listed_by_name_with_their_items_by_name(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    owner_conn.execute(
        "UPDATE setup.expense_items SET stopped_on = %s WHERE id = %s", (TODAY, catalogue.tyres)
    )
    owner_conn.execute(
        "UPDATE setup.expense_categories SET stopped_on = %s WHERE id = %s",
        (date(2026, 3, 6), catalogue.loans),
    )
    page = read(app_conn, "setup_expense_category_list", catalogue.owner, 1, 25)
    assert page["total"] == 3
    assert [c["name"] for c in page["items"]] == ["Charges", "Garage and repairs", "Loans"]
    garage = page["items"][1]
    assert garage == {
        "id": str(catalogue.garage),
        "name": "Garage and repairs",
        "bucket": 1,
        "main_category_id": str(catalogue.repairs),
        "main_category_name": "Repairs",
        "active": True,
        "stopped_on": None,
        "items": [
            {
                "id": str(catalogue.towing),
                "category_id": str(catalogue.garage),
                "name": "Towing",
                "active": True,
                "stopped_on": None,
            },
            {
                "id": str(catalogue.tyres),
                "category_id": str(catalogue.garage),
                "name": "Tyres",
                "active": False,
                "stopped_on": "2026-03-05",
            },
        ],
    }
    loans = page["items"][2]
    assert (loans["active"], loans["stopped_on"]) == (True, "2026-03-06")
    assert (loans["main_category_id"], loans["main_category_name"]) == (None, None)


def test_categories_page_by_name(app_conn: Conn, catalogue: Catalogue) -> None:
    page = read(app_conn, "setup_expense_category_list", catalogue.owner, 2, 1)
    assert page["total"] == 3
    (only,) = page["items"]
    assert (only["name"], len(only["items"])) == ("Garage and repairs", 2)
    refuses(
        app_conn,
        "setup_expense_category_list",
        catalogue.owner,
        [1, 101],
        "XC422",
        "page_out_of_range",
    )


def test_the_options_leave_out_stopped_items_and_items_of_stopped_categories(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    owner_conn.execute(
        "UPDATE setup.expense_items SET stopped_on = %s WHERE id = %s", (TODAY, catalogue.tyres)
    )
    owner_conn.execute(
        "UPDATE setup.expense_categories SET stopped_on = %s WHERE id = %s",
        (date(2026, 3, 1), catalogue.loans),
    )
    owner_conn.execute(
        "UPDATE setup.expense_items SET stopped_on = %s WHERE id = %s",
        (date(2026, 3, 6), catalogue.towing),
    )
    options = read(app_conn, "setup_expense_item_options", catalogue.owner)
    assert options == [
        {
            "id": str(catalogue.insurance),
            "name": "Insurance",
            "category_id": str(catalogue.charges),
            "category_name": "Charges",
            "bucket": 2,
            "main_category_id": None,
            "main_category_name": None,
        },
        {
            "id": str(catalogue.parking),
            "name": "Parking",
            "category_id": str(catalogue.charges),
            "category_name": "Charges",
            "bucket": 2,
            "main_category_id": None,
            "main_category_name": None,
        },
        {
            "id": str(catalogue.towing),
            "name": "Towing",
            "category_id": str(catalogue.garage),
            "category_name": "Garage and repairs",
            "bucket": 1,
            "main_category_id": str(catalogue.repairs),
            "main_category_name": "Repairs",
        },
    ]


@pytest.mark.parametrize(
    ("grant", "can_list", "can_pick"),
    [
        (None, False, False),
        ("catalog.view", True, True),
        ("expenses.view", True, True),
        ("scheduled.view", True, True),
        ("expenses.capture", True, True),
        ("scheduled.add", True, True),
        ("scheduled.edit", True, True),
        ("pettycash.spend", False, True),
        ("savings.view", False, False),
        ("savings.edit", False, False),
    ],
)
def test_reading_needs_catalogue_expense_or_schedule_access(
    app_conn: Conn,
    owner_conn: Conn,
    catalogue: Catalogue,
    grant: str | None,
    can_list: bool,
    can_pick: bool,
) -> None:
    if grant is not None:
        set_override(owner_conn, catalogue.clerk, grant)
    if can_list:
        assert read(app_conn, "setup_expense_category_list", catalogue.clerk, 1, 25)["total"] == 3
    else:
        refuses(
            app_conn,
            "setup_expense_category_list",
            catalogue.clerk,
            [1, 25],
            "XC403",
            "permission_missing",
        )
    if can_pick:
        assert len(read(app_conn, "setup_expense_item_options", catalogue.clerk)) == 5
    else:
        refuses(
            app_conn,
            "setup_expense_item_options",
            catalogue.clerk,
            [],
            "XC403",
            "permission_missing",
        )


def _writes(catalogue: Catalogue) -> dict[str, list[tuple[str, list[Any]]]]:
    return {
        "catalog.add": [
            ("setup_expense_category_create", ["Road costs", None]),
            ("setup_expense_item_create", [catalogue.loans, "Interest"]),
            ("setup_expense_main_category_create", ["Finance"]),
        ],
        "catalog.edit": [
            ("setup_expense_category_update", [catalogue.loans, "Bank loans", None, False]),
            ("setup_expense_item_rename", [catalogue.tyres, "Tyres and tubes"]),
            ("setup_expense_main_category_rename", [catalogue.repairs, "Garage"]),
        ],
        "catalog.stop": [
            ("setup_expense_category_set_stopped", [catalogue.loans, True]),
            ("setup_expense_item_set_stopped", [catalogue.tyres, True]),
        ],
    }


@pytest.mark.parametrize("missing", ["catalog.add", "catalog.edit", "catalog.stop"])
def test_each_catalogue_write_needs_its_own_right(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue, missing: str
) -> None:
    for right in ("catalog.view", "catalog.add", "catalog.edit", "catalog.stop", "scheduled.edit"):
        if right != missing:
            set_override(owner_conn, catalogue.clerk, right)
    writes = _writes(catalogue)
    for routine, args in writes.pop(missing):
        refuses(app_conn, routine, catalogue.clerk, args, "XC403", "permission_missing")
    for allowed in writes.values():
        for routine, args in allowed:
            assert run(app_conn, routine, catalogue.clerk, *args)["outcome"] != "unchanged"


def test_another_organization_cannot_read_the_catalogue(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    other = seed_organization(owner_conn)
    refused(
        app_conn,
        "setup_expense_category_list",
        [other.user, catalogue.owner.org, REQUEST, 1, 25, T0],
        "XC403",
        "not_member",
    )


# --- categories -----------------------------------------------------------------------


def test_a_category_is_created_trimmed_and_logged(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    org = catalogue.owner.org
    before = settings_version(owner_conn, org)
    result = run(app_conn, "setup_expense_category_create", catalogue.owner, " Road costs ", None)
    category = UUID(str(result["id"]))
    assert (result["outcome"], result["version"]) == ("created", before + 1)
    row = _category(owner_conn, category)
    assert (row["name"], row["bucket"], row["main_category_id"]) == ("Road costs", None, None)
    (log,) = change_rows(owner_conn, org, "expenses")
    assert (log["entity_id"], log["vehicle_id"], log["before"]) == (category, None, "null")
    assert log["reason"] == "Added expense category Road costs"
    assert log["after"] == (
        f'{{"Id":"{category}","Name":"Road costs","MainCategoryId":null,"StoppedOn":null}}'
    )


def test_a_category_is_created_under_a_main_category_and_says_so(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    result = run(
        app_conn, "setup_expense_category_create", catalogue.owner, "Brakes", catalogue.repairs
    )
    row = _category(owner_conn, UUID(str(result["id"])))
    assert (row["main_category_id"], row["bucket"]) == (catalogue.repairs, None)
    assert reasons(owner_conn, catalogue.owner.org, "expenses") == [
        "Added expense category Brakes under Repairs"
    ]


@pytest.mark.parametrize("name", [None, " ", "x" * 101])
def test_a_category_name_must_be_1_to_100_characters(
    app_conn: Conn, catalogue: Catalogue, name: str | None
) -> None:
    refuses(
        app_conn,
        "setup_expense_category_create",
        catalogue.owner,
        [name, UUID(int=1)],
        "XC422",
        "expense_name_length",
    )


def test_a_category_needs_a_known_main_category_or_none(
    app_conn: Conn, catalogue: Catalogue
) -> None:
    refuses(
        app_conn,
        "setup_expense_category_create",
        catalogue.owner,
        ["Road costs", UUID(int=1)],
        "XC404",
        "not_found",
    )


def test_a_category_name_is_unique_ignoring_case(app_conn: Conn, catalogue: Catalogue) -> None:
    refuses(
        app_conn,
        "setup_expense_category_create",
        catalogue.owner,
        ["CHARGES", None],
        "XC422",
        "expense_category_taken",
    )


def test_the_rename_and_move_reasons(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    owner, loans, repairs = catalogue.owner, catalogue.loans, catalogue.repairs
    update = "setup_expense_category_update"
    run(app_conn, update, owner, loans, "Bank loans", repairs, False)
    run(app_conn, update, owner, loans, "Bank loans", repairs, True)
    run(app_conn, update, owner, loans, "Loans", None, True)
    run(app_conn, update, owner, loans, "Loans", repairs, True)
    run(app_conn, update, owner, loans, "Bank loans", None, True)
    assert reasons(owner_conn, owner.org, "expenses") == [
        "Renamed expense category Loans to Bank loans",
        "Moved expense category Bank loans to main category Repairs",
        "Renamed expense category Bank loans to Loans, moved to no main category",
        "Moved expense category Loans to main category Repairs",
        "Renamed expense category Loans to Bank loans, moved to no main category",
    ]
    assert _category(owner_conn, loans)["bucket"] == 3
    third = change_rows(owner_conn, owner.org, "expenses")[2]
    assert json.loads(third["before"]) == {
        "Id": str(loans),
        "Name": "Bank loans",
        "MainCategoryId": str(repairs),
        "StoppedOn": None,
    }


def test_a_category_saved_as_it_is_is_unchanged(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    version = settings_version(owner_conn, catalogue.owner.org)
    for main, given in [(None, True), (catalogue.repairs, False), (UUID(int=1), False)]:
        result = run(
            app_conn,
            "setup_expense_category_update",
            catalogue.owner,
            catalogue.loans,
            " Loans ",
            main,
            given,
        )
        assert (result["outcome"], result["version"]) == ("unchanged", version)
    assert change_rows(owner_conn, catalogue.owner.org, "expenses") == []


def test_a_category_update_checks_name_then_record_then_main_category_then_uniqueness(
    app_conn: Conn, catalogue: Catalogue
) -> None:
    owner = catalogue.owner
    for args, sqlstate, code in [
        ([UUID(int=1), "", UUID(int=2), True], "XC422", "expense_name_length"),
        ([UUID(int=1), "Fresh", UUID(int=2), True], "XC404", "not_found"),
        ([catalogue.loans, "charges", UUID(int=2), True], "XC404", "not_found"),
        ([catalogue.loans, "charges", None, True], "XC422", "expense_category_taken"),
    ]:
        refuses(app_conn, "setup_expense_category_update", owner, args, sqlstate, code)


def test_turning_a_category_off_and_on(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    owner = catalogue.owner
    first = run(app_conn, "setup_expense_category_set_stopped", owner, catalogue.loans, True)
    again = run(app_conn, "setup_expense_category_set_stopped", owner, catalogue.loans, True)
    assert (first["outcome"], again["outcome"]) == ("updated", "unchanged")
    assert _category(owner_conn, catalogue.loans)["stopped_on"] == TODAY
    run(app_conn, "setup_expense_category_set_stopped", owner, catalogue.loans, False)
    assert _category(owner_conn, catalogue.loans)["stopped_on"] is None
    assert (
        run(app_conn, "setup_expense_category_set_stopped", owner, catalogue.loans, False)[
            "outcome"
        ]
        == "unchanged"
    )
    assert reasons(owner_conn, owner.org, "expenses") == [
        "Turned off expense category Loans",
        "Turned on expense category Loans",
    ]


@pytest.mark.parametrize("stopped_on", [date(2026, 3, 2), date(2026, 3, 8)])
def test_a_category_stopped_on_another_date_must_be_turned_on_first(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue, stopped_on: date
) -> None:
    owner_conn.execute(
        "UPDATE setup.expense_categories SET stopped_on = %s WHERE id = %s",
        (stopped_on, catalogue.loans),
    )
    refuses(
        app_conn,
        "setup_expense_category_set_stopped",
        catalogue.owner,
        [catalogue.loans, True],
        "XC422",
        "expense_already_stopped",
    )
    run(app_conn, "setup_expense_category_set_stopped", catalogue.owner, catalogue.loans, False)
    assert _category(owner_conn, catalogue.loans)["stopped_on"] is None
    refuses(
        app_conn,
        "setup_expense_category_set_stopped",
        catalogue.owner,
        [UUID(int=1), True],
        "XC404",
        "not_found",
    )


# --- items ----------------------------------------------------------------------------


def test_an_item_is_added_under_its_category(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    result = run(
        app_conn, "setup_expense_item_create", catalogue.owner, catalogue.charges, " Tolls "
    )
    item = UUID(str(result["id"]))
    assert (_item(owner_conn, item)["name"], _item(owner_conn, item)["category_id"]) == (
        "Tolls",
        catalogue.charges,
    )
    (row,) = change_rows(owner_conn, catalogue.owner.org, "expenses")
    assert (row["entity_id"], row["reason"]) == (item, "Added expense item Tolls under Charges")
    assert row["after"] == (
        f'{{"Id":"{item}","CategoryId":"{catalogue.charges}","Name":"Tolls","StoppedOn":null}}'
    )


def test_an_item_name_is_unique_within_its_category_ignoring_case(
    app_conn: Conn, catalogue: Catalogue
) -> None:
    refuses(
        app_conn,
        "setup_expense_item_create",
        catalogue.owner,
        [catalogue.charges, "parking"],
        "XC422",
        "expense_item_taken",
    )
    assert (
        run(app_conn, "setup_expense_item_create", catalogue.owner, catalogue.garage, "Parking")[
            "outcome"
        ]
        == "created"
    )


def test_a_stopped_category_still_accepts_items(
    app_conn: Conn, owner_conn: Conn, catalogue: Catalogue
) -> None:
    owner_conn.execute(
        "UPDATE setup.expense_categories SET stopped_on = %s WHERE id = %s",
        (date(2026, 3, 1), catalogue.loans),
    )
    assert (
        run(app_conn, "setup_expense_item_create", catalogue.owner, catalogue.loans, "Interest")[
            "outcome"
        ]
        == "created"
    )


def test_an_item_needs_a_known_category_and_a_name(app_conn: Conn, catalogue: Catalogue) -> None:
    refuses(
        app_conn,
        "setup_expense_item_create",
        catalogue.owner,
        [UUID(int=1), ""],
        "XC404",
        "not_found",
    )
    refuses(
        app_conn,
        "setup_expense_item_create",
        catalogue.owner,
        [catalogue.charges, "x" * 101],
        "XC422",
        "expense_name_length",
    )


def test_renaming_an_item(app_conn: Conn, owner_conn: Conn, catalogue: Catalogue) -> None:
    owner = catalogue.owner
    result = run(app_conn, "setup_expense_item_rename", owner, catalogue.towing, "Road towing")
    assert (result["id"], result["outcome"]) == (catalogue.towing, "updated")
    unchanged = run(app_conn, "setup_expense_item_rename", owner, catalogue.towing, "Road towing")
    assert unchanged["outcome"] == "unchanged"
    assert reasons(owner_conn, owner.org, "expenses") == [
        "Renamed expense item Towing to Road towing"
    ]
    for args, sqlstate, code in [
        ([UUID(int=1), " "], "XC422", "expense_name_length"),
        ([UUID(int=1), "Tyres"], "XC404", "not_found"),
        ([catalogue.towing, "TYRES"], "XC422", "expense_item_taken"),
    ]:
        refuses(app_conn, "setup_expense_item_rename", owner, args, sqlstate, code)
    assert (
        run(app_conn, "setup_expense_item_rename", owner, catalogue.towing, "Insurance")["outcome"]
        == "updated"
    )


def test_turning_an_item_off_and_on(app_conn: Conn, owner_conn: Conn, catalogue: Catalogue) -> None:
    owner = catalogue.owner
    run(app_conn, "setup_expense_item_set_stopped", owner, catalogue.tyres, True)
    assert (
        run(app_conn, "setup_expense_item_set_stopped", owner, catalogue.tyres, True)["outcome"]
        == "unchanged"
    )
    assert _item(owner_conn, catalogue.tyres)["stopped_on"] == TODAY
    run(app_conn, "setup_expense_item_set_stopped", owner, catalogue.tyres, False)
    assert reasons(owner_conn, owner.org, "expenses") == [
        "Turned off expense item Tyres",
        "Turned on expense item Tyres",
    ]
    owner_conn.execute(
        "UPDATE setup.expense_items SET stopped_on = %s WHERE id = %s",
        (date(2026, 3, 7), catalogue.towing),
    )
    refuses(
        app_conn,
        "setup_expense_item_set_stopped",
        owner,
        [catalogue.towing, True],
        "XC422",
        "expense_already_stopped",
    )
    refuses(
        app_conn,
        "setup_expense_item_set_stopped",
        owner,
        [UUID(int=1), False],
        "XC404",
        "not_found",
    )
