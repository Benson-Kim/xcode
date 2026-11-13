"""The setup delete routines (``api.setup_expense_main_category_delete``,
``api.setup_expense_category_delete``, ``api.setup_expense_item_delete``,
``api.setup_vehicle_delete``, ``api.setup_company_delete``), called as ``xcode_app``: a record
nothing refers to is deleted and the change log keeps what it held; each kind of reference
refuses with ``XC409 in_use`` and the ``{name, use}`` detail and leaves every row in place; a
foreign key added later still refuses; another organization's record is not found and a caller
without the right is refused. The structure test holds the rule the routines rely on: every
foreign key to these tables is checked at once and never cascades."""

from __future__ import annotations

import json
from collections.abc import Callable
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
    add_category,
    add_central_expense,
    add_investment,
    add_item,
    add_main_category,
    add_pettycash_spend,
    add_record,
    add_schedule,
    change_rows,
    refuses,
    run,
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
WEEK = [Decimal(d) for d in ("1000", "1000", "1000", "1000", "1000", "1500", "500")]
DELETES = {
    "main_category": "setup_expense_main_category_delete",
    "category": "setup_expense_category_delete",
    "item": "setup_expense_item_delete",
    "vehicle": "setup_vehicle_delete",
    "company": "setup_company_delete",
}
TABLES = {
    "main_category": "expense_main_categories",
    "category": "expense_categories",
    "item": "expense_items",
    "vehicle": "fleet_vehicles",
    "company": "psv_companies",
}


@dataclass(frozen=True, slots=True)
class Yard:
    owner: Member
    clerk: Member
    company: UUID
    spare: UUID
    other_vehicle: UUID
    main: UUID
    category: UUID
    item: UUID


@pytest.fixture
def yard(operator_conn: Conn, owner_conn: Conn) -> Yard:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 2, "Revenue clerk", "Cleo", "Clerk")
    org = owner.org
    set_organization(owner_conn, org, business_date=TODAY)
    company = add_company(owner_conn, org, "North Star")
    spare = add_company(owner_conn, org, "Spare Line")
    other_vehicle = add_vehicle(owner_conn, org, company, "KDB 111A", joined_on=date(2026, 1, 1))
    main = add_main_category(owner_conn, org, "Running")
    category = add_category(owner_conn, org, "Fuel", main_category=main)
    item = add_item(owner_conn, org, category, "Diesel")
    return Yard(owner, clerk, company, spare, other_vehicle, main, category, item)


def _new_vehicle(app_conn: Conn, yard: Yard, registration: str = "KDA 482M") -> UUID:
    result = run(
        app_conn,
        "setup_vehicle_create",
        yard.owner,
        yard.company,
        registration,
        "N-7",
        date(2026, 3, 1),
        WEEK,
        None,
        None,
    )
    return UUID(str(result["id"]))


def _exists(owner_conn: Conn, record: str, record_id: UUID) -> bool:
    row = owner_conn.execute(
        f"SELECT count(*) AS n FROM setup.{TABLES[record]} WHERE id = %s", (record_id,)
    ).fetchone()
    assert row is not None
    return bool(row["n"])


def _target_sets(owner_conn: Conn, vehicle: UUID) -> int:
    row = owner_conn.execute(
        "SELECT count(*) AS n FROM setup.vehicle_target_sets WHERE vehicle_id = %s", (vehicle,)
    ).fetchone()
    assert row is not None
    return int(row["n"])


def _in_use(
    app_conn: Conn, owner_conn: Conn, yard: Yard, record: str, record_id: UUID
) -> dict[str, Any]:
    version = settings_version(owner_conn, yard.owner.org)
    error = refuses(app_conn, DELETES[record], yard.owner, [record_id], "XC409", "in_use")
    assert _exists(owner_conn, record, record_id)
    assert settings_version(owner_conn, yard.owner.org) == version
    detail: dict[str, Any] = json.loads(error.diag.message_detail or "{}")
    return detail


def _saving(owner_conn: Conn, yard: Yard) -> tuple[UUID, UUID]:
    """A saving shared to the other vehicle only, so the vehicle under test is referred to by
    nothing but the opening amount or the run a test adds."""
    item, (version,) = add_schedule(
        owner_conn,
        yard.owner.org,
        Version(date(2026, 1, 1), {yard.other_vehicle: 100}, name="Tyre fund", kind=2, day=1),
    )
    return item, version


# --- deleted while nothing refers to it --------------------------------------------------


def test_an_unused_main_category_is_deleted_and_the_log_keeps_it(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    main = add_main_category(owner_conn, org, "Admin costs")
    before = settings_version(owner_conn, org)
    result = run(app_conn, DELETES["main_category"], yard.owner, main)
    assert result == {"id": main, "version": before + 1, "outcome": "updated"}
    assert not _exists(owner_conn, "main_category", main)
    (row,) = change_rows(owner_conn, org, "expenses")
    assert (row["entity_id"], row["vehicle_id"]) == (main, None)
    assert row["reason"] == "Deleted main category Admin costs"
    assert json.loads(row["before"]) == {"Id": str(main), "Name": "Admin costs"}
    assert row["after"] == "null"
    (audit,) = audit_events(owner_conn, org, "setup.expenses")
    assert audit["after"] is None
    refuses(app_conn, DELETES["main_category"], yard.owner, [main], "XC404", "not_found")


def test_an_unused_category_and_item_are_deleted(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    category = add_category(owner_conn, org, "Tyres", main_category=yard.main)
    item = add_item(owner_conn, org, category, "Front tyre")
    run(app_conn, DELETES["item"], yard.owner, item)
    run(app_conn, DELETES["category"], yard.owner, category)
    assert not _exists(owner_conn, "item", item)
    assert not _exists(owner_conn, "category", category)
    item_log, category_log = change_rows(owner_conn, org, "expenses")
    assert item_log["reason"] == "Deleted expense item Front tyre"
    assert json.loads(item_log["before"]) == {
        "Id": str(item),
        "CategoryId": str(category),
        "Name": "Front tyre",
        "StoppedOn": None,
    }
    assert category_log["reason"] == "Deleted expense category Tyres"
    assert json.loads(category_log["before"]) == {
        "Id": str(category),
        "Name": "Tyres",
        "MainCategoryId": str(yard.main),
        "StoppedOn": None,
    }
    assert (item_log["after"], category_log["after"]) == ("null", "null")


def test_an_unused_vehicle_is_deleted_with_its_target_sets(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    vehicle = _new_vehicle(app_conn, yard)
    assert _target_sets(owner_conn, vehicle) == 1
    result = run(app_conn, DELETES["vehicle"], yard.owner, vehicle)
    assert result["outcome"] == "updated"
    assert not _exists(owner_conn, "vehicle", vehicle)
    assert _target_sets(owner_conn, vehicle) == 0
    *_, row = change_rows(owner_conn, org, "vehicles")
    assert (row["entity_id"], row["vehicle_id"]) == (vehicle, vehicle)
    assert row["reason"] == "Deleted vehicle KDA 482M"
    before = json.loads(row["before"])
    assert (before["Id"], before["Registration"], before["CompanyId"]) == (
        str(vehicle),
        "KDA 482M",
        str(yard.company),
    )
    assert [s["StartsOn"] for s in before["TargetSets"]] == ["2026-03-01"]
    assert row["after"] == "null"


def test_an_unused_company_is_deleted(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    org = yard.owner.org
    run(app_conn, DELETES["company"], yard.owner, yard.spare)
    assert not _exists(owner_conn, "company", yard.spare)
    (row,) = change_rows(owner_conn, org, "companies")
    assert row["entity_id"] == yard.spare
    assert row["reason"] == "Deleted company Spare Line"
    assert json.loads(row["before"]) == {
        "Id": str(yard.spare),
        "Name": "Spare Line",
        "ArchivedOn": None,
        "Active": True,
    }
    assert row["after"] == "null"


# --- refused while anything refers to it -------------------------------------------------


def test_a_main_category_with_categories_is_in_use(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    detail = _in_use(app_conn, owner_conn, yard, "main_category", yard.main)
    assert detail == {"name": "Running", "use": "main_category_categories"}
    assert change_rows(owner_conn, yard.owner.org, "expenses") == []


def test_a_category_with_items_is_in_use(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    detail = _in_use(app_conn, owner_conn, yard, "category", yard.category)
    assert detail == {"name": "Fuel", "use": "category_items"}


def _item_schedule(conn: Conn, y: Yard) -> None:
    add_schedule(
        conn, y.owner.org, Version(date(2026, 1, 1), {y.other_vehicle: 300}, expense_item_id=y.item)
    )


ITEM_USES: dict[str, Callable[[Conn, Yard], None]] = {
    "item_expenses": lambda conn, y: add_central_expense(
        conn, y.owner.org, y.other_vehicle, y.item, recorder=y.owner.id
    ),
    "item_pettycash": lambda conn, y: add_pettycash_spend(
        conn, y.owner.org, y.other_vehicle, y.item, holder=y.owner.id
    ),
    "item_schedules": _item_schedule,
}


@pytest.mark.parametrize("use", sorted(ITEM_USES))
def test_an_item_that_is_used_is_in_use(
    app_conn: Conn, owner_conn: Conn, yard: Yard, use: str
) -> None:
    ITEM_USES[use](owner_conn, yard)
    assert _in_use(app_conn, owner_conn, yard, "item", yard.item) == {"name": "Diesel", "use": use}


def _vehicle_uses() -> dict[str, Callable[[Conn, Yard, UUID], None]]:
    def revenue(conn: Conn, y: Yard, v: UUID) -> None:
        add_record(conn, y.owner.org, v, date(2026, 3, 2), 1500, recorder=y.owner.id)

    def investment(conn: Conn, y: Yard, v: UUID) -> None:
        add_investment(conn, y.owner.org, v, date(2026, 3, 2), "Deposit", 500, recorder=y.owner.id)

    def away(conn: Conn, y: Yard, v: UUID) -> None:
        add_away(conn, y.owner.org, v, date(2026, 3, 5), date(2026, 3, 7))

    def schedule(conn: Conn, y: Yard, v: UUID) -> None:
        add_schedule(conn, y.owner.org, Version(date(2026, 1, 1), {v: 100}))

    def opening(conn: Conn, y: Yard, v: UUID) -> None:
        item, _ = _saving(conn, y)
        conn.execute(
            "INSERT INTO setup.saving_openings (organization_id, item_id, opened_on) "
            "VALUES (%s, %s, DATE '2026-01-15')",
            (y.owner.org, item),
        )
        conn.execute(
            "INSERT INTO setup.saving_opening_amounts (organization_id, item_id, vehicle_id, "
            "amount) VALUES (%s, %s, %s, 500)",
            (y.owner.org, item, v),
        )

    def run_of_saving(conn: Conn, y: Yard, v: UUID) -> None:
        item, version = _saving(conn, y)
        conn.execute(
            "INSERT INTO setup.saving_runs (organization_id, item_id, run_on, vehicle_id, "
            "version_id, amount, state, revenue, decided_at) "
            "VALUES (%s, %s, DATE '2026-03-02', %s, %s, 100, 1, 2500, now())",
            (y.owner.org, item, v, version),
        )

    def scope(conn: Conn, y: Yard, v: UUID) -> None:
        set_scope(conn, y.clerk, y.owner.org, vehicles=[v])

    return {
        "vehicle_revenue": revenue,
        "vehicle_pettycash": lambda conn, y, v: add_pettycash_spend(
            conn, y.owner.org, v, y.item, holder=y.owner.id
        ),
        "vehicle_expenses": lambda conn, y, v: add_central_expense(
            conn, y.owner.org, v, y.item, recorder=y.owner.id
        ),
        "vehicle_investments": investment,
        "vehicle_away": away,
        "vehicle_schedules": schedule,
        "vehicle_savings:opening": opening,
        "vehicle_savings:run": run_of_saving,
        "vehicle_scope": scope,
    }


VEHICLE_USES = _vehicle_uses()


@pytest.mark.parametrize("case", sorted(VEHICLE_USES))
def test_a_vehicle_that_anything_refers_to_is_in_use_and_keeps_its_target_sets(
    app_conn: Conn, owner_conn: Conn, yard: Yard, case: str
) -> None:
    vehicle = _new_vehicle(app_conn, yard)
    VEHICLE_USES[case](owner_conn, yard, vehicle)
    detail = _in_use(app_conn, owner_conn, yard, "vehicle", vehicle)
    assert detail == {"name": "KDA 482M", "use": case.split(":", maxsplit=1)[0]}
    assert _target_sets(owner_conn, vehicle) == 1


def test_a_company_with_vehicles_is_in_use(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    detail = _in_use(app_conn, owner_conn, yard, "company", yard.company)
    assert detail == {"name": "North Star", "use": "company_vehicles"}


def test_a_company_in_a_data_scope_is_in_use(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    set_scope(owner_conn, yard.clerk, yard.owner.org, companies=[yard.spare])
    detail = _in_use(app_conn, owner_conn, yard, "company", yard.spare)
    assert detail == {"name": "Spare Line", "use": "company_scope"}


def test_a_foreign_key_added_later_still_refuses(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    owner_conn.execute(
        "CREATE TABLE setup.later_references (organization_id uuid NOT NULL, item_id uuid "
        "NOT NULL, FOREIGN KEY (organization_id, item_id) REFERENCES setup.expense_items "
        "(organization_id, id))"
    )
    item = add_item(owner_conn, yard.owner.org, yard.category, "Engine oil")
    owner_conn.execute("INSERT INTO setup.later_references VALUES (%s, %s)", (yard.owner.org, item))
    detail = _in_use(app_conn, owner_conn, yard, "item", item)
    assert detail == {"name": "Engine oil", "use": "item_other"}


# --- reach and rights --------------------------------------------------------------------


def _records(app_conn: Conn, owner_conn: Conn, yard: Yard) -> dict[str, UUID]:
    org = yard.owner.org
    main = add_main_category(owner_conn, org, "Spare main")
    category = add_category(owner_conn, org, "Spare category")
    return {
        "main_category": main,
        "category": category,
        "item": add_item(owner_conn, org, yard.category, "Spare item"),
        "vehicle": _new_vehicle(app_conn, yard, "KDC 200B"),
        "company": yard.spare,
    }


def test_without_the_right_each_delete_is_refused(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    for record, record_id in _records(app_conn, owner_conn, yard).items():
        refuses(app_conn, DELETES[record], yard.clerk, [record_id], "XC403", "permission_missing")
        assert _exists(owner_conn, record, record_id), record


@pytest.mark.parametrize(
    ("record", "right"),
    [
        ("main_category", "catalog.stop"),
        ("category", "catalog.stop"),
        ("item", "catalog.stop"),
        ("vehicle", "vehicles.edit"),
        ("company", "companies.edit"),
    ],
)
def test_each_delete_needs_its_right_and_nothing_more(
    app_conn: Conn, owner_conn: Conn, yard: Yard, record: str, right: str
) -> None:
    record_id = _records(app_conn, owner_conn, yard)[record]
    set_scope(owner_conn, yard.clerk, yard.owner.org, all_companies=True)
    set_override(owner_conn, yard.clerk, right)
    assert run(app_conn, DELETES[record], yard.clerk, record_id)["outcome"] == "updated"


def test_a_scoped_caller_cannot_reach_a_vehicle_or_company_outside_the_scope(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    manager = provision_member(operator_conn, 3, "Revenue clerk", "Sam", "Scoped")
    for right in ("vehicles.edit", "companies.edit"):
        set_override(owner_conn, manager, right)
    elsewhere = add_company(owner_conn, yard.owner.org, "Elsewhere")
    set_scope(owner_conn, manager, manager.org, companies=[elsewhere])
    vehicle = _new_vehicle(app_conn, yard)
    refuses(app_conn, DELETES["vehicle"], manager, [vehicle], "XC404", "not_found")
    refuses(app_conn, DELETES["company"], manager, [yard.spare], "XC404", "not_found")
    assert _exists(owner_conn, "vehicle", vehicle)
    assert _exists(owner_conn, "company", yard.spare)


def test_another_organization_cannot_reach_these_records(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    other = seed_organization(owner_conn)
    records = _records(app_conn, owner_conn, yard)
    for record, record_id in records.items():
        refused(
            app_conn,
            DELETES[record],
            [other.user, other.org, REQUEST, record_id, T0],
            "XC404",
            "not_found",
        )
        refused(
            app_conn,
            DELETES[record],
            [other.user, yard.owner.org, REQUEST, record_id, T0],
            "XC403",
            "not_member",
        )
        assert _exists(owner_conn, record, record_id), record


def test_an_unknown_id_is_not_found(app_conn: Conn, yard: Yard) -> None:
    unknown = UUID("00000000-0000-4000-8000-000000000000")
    for routine in DELETES.values():
        refuses(app_conn, routine, yard.owner, [unknown], "XC404", "not_found")


# --- the foreign keys the routines rely on ------------------------------------------------


def test_the_executor_may_delete_and_every_reference_is_a_plain_immediate_foreign_key(
    owner_conn: Conn,
) -> None:
    for table in TABLES.values():
        row = owner_conn.execute(
            "SELECT has_table_privilege('xcode_api_executor', %s, 'DELETE') AS d",
            (f"setup.{table}",),
        ).fetchone()
        assert row == {"d": True}, table
    rows = owner_conn.execute(
        "SELECT c.confrelid::regclass::text AS target, c.conrelid::regclass::text AS source, "
        "c.confdeltype AS on_delete, c.condeferrable AS deferrable "
        "FROM pg_catalog.pg_constraint AS c WHERE c.contype = 'f' AND c.confrelid = ANY "
        "(ARRAY['setup.expense_main_categories', 'setup.expense_categories', "
        "'setup.expense_items', 'setup.fleet_vehicles', 'setup.psv_companies']::regclass[])"
    ).fetchall()
    assert {(r["on_delete"], r["deferrable"]) for r in rows} == {("a", False)}
    named = {
        "setup.expense_main_categories": {"setup.expense_categories"},
        "setup.expense_categories": {"setup.expense_items"},
        "setup.expense_items": {
            "expenses.entries",
            "pettycash.entries",
            "setup.recurring_versions",
        },
        "setup.fleet_vehicles": {
            "expenses.entries",
            "pettycash.entries",
            "revenue.records",
            "setup.recurring_allocations",
            "setup.saving_opening_amounts",
            "setup.saving_runs",
            "setup.vehicle_away_periods",
            "setup.vehicle_investments",
            "setup.vehicle_target_sets",
            "tenancy.data_scope_vehicles",
        },
        "setup.psv_companies": {"setup.fleet_vehicles", "tenancy.data_scope_companies"},
    }
    found: dict[str, set[str]] = {}
    for r in rows:
        found.setdefault(r["target"], set()).add(r["source"])
    assert found == named
