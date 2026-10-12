"""The scheduled-item routines (``api.setup_recurring_*``, ``api.setup_vehicle_options``),
called as ``xcode_app``: one test per step of the save and per ``recurring_*`` code, the
``unchanged`` revise, the share rules (a vehicle already on the item is exempt, the first bad
share decides), the dated revisions, the change sentences with one, two and three parts, the
stop and cancel-stop states, and a scoped viewer's list.

The business date is Sunday 2026-03-15. Items older than the business date are seeded as
``xcode_owner``, because a save can never start before the first of the business month."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn
from ..support.setup_rows import (
    Definition,
    Version,
    add_category,
    add_item,
    add_schedule,
    change_rows,
    read,
    reasons,
    refuses,
    run,
    shares,
)
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
    settings_version,
)

TODAY = date(2026, 3, 15)
COSTS = ("scheduled.view", "scheduled.add", "scheduled.edit")
SAVINGS = ("savings.view", "savings.add", "savings.edit")


@dataclass(frozen=True, slots=True)
class Rules:
    owner: Member
    clerk: Member
    north: UUID
    south: UUID
    kda: UUID
    kdb: UUID
    kdc: UUID
    charges: UUID
    loans: UUID
    parking: UUID
    insurance: UUID
    spares: UUID
    towing: UUID
    repayment: UUID


@pytest.fixture
def rules(operator_conn: Conn, owner_conn: Conn) -> Rules:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 2, "Revenue clerk", "Cleo", "Clerk")
    set_organization(owner_conn, owner.org, business_date=TODAY)
    org = owner.org
    north = add_company(owner_conn, org, "North Star")
    south = add_company(owner_conn, org, "South Line")
    charges = add_category(owner_conn, org, "Charges", bucket=2)
    garage = add_category(owner_conn, org, "Garage and repairs", bucket=1)
    loans = add_category(owner_conn, org, "Loans", bucket=3)
    return Rules(
        owner=owner,
        clerk=clerk,
        north=north,
        south=south,
        kda=add_vehicle(owner_conn, org, north, "KDA 482M"),
        kdb=add_vehicle(owner_conn, org, north, "KDB 111A"),
        kdc=add_vehicle(owner_conn, org, south, "KDC 200B"),
        charges=charges,
        loans=loans,
        parking=add_item(owner_conn, org, charges, "Parking"),
        insurance=add_item(owner_conn, org, charges, "Insurance"),
        spares=add_item(owner_conn, org, garage, "Spares"),
        towing=add_item(owner_conn, org, garage, "Towing"),
        repayment=add_item(owner_conn, org, loans, "Loan repayment"),
    )


def _saving(rules: Rules, **changes: Any) -> Definition:
    base = Definition(
        allocations=shares((rules.kda, 1000)),
        amount=1000,
        name="Owner savings",
        kind=2,
        frequency=2,
        day=5,
        start=TODAY,
    )
    return replace(base, **changes)


def _cost(rules: Rules, **changes: Any) -> Definition:
    base = Definition(
        allocations=shares((rules.kda, 1200)),
        amount=1200,
        name="Typed name",
        kind=1,
        frequency=2,
        day=6,
        start=TODAY,
        expense_item_id=rules.parking,
    )
    return replace(base, **changes)


def _create(app: Conn, who: Member, definition: Definition) -> UUID:
    return UUID(str(run(app, "setup_recurring_create", who, *definition.args())["id"]))


def _revise(app: Conn, who: Member, item: UUID, definition: Definition) -> dict[str, Any]:
    return run(app, "setup_recurring_revise", who, item, *definition.args())


def _create_refused(
    app: Conn, who: Member, definition: Definition, sqlstate: str, code: str
) -> None:
    refuses(app, "setup_recurring_create", who, definition.args(), sqlstate, code)


def _revise_refused(
    app: Conn, who: Member, item: UUID, definition: Definition, sqlstate: str, code: str
) -> None:
    refuses(app, "setup_recurring_revise", who, [item, *definition.args()], sqlstate, code)


def _versions(owner_conn: Conn, item: UUID) -> list[dict[str, Any]]:
    return owner_conn.execute(
        "SELECT * FROM setup.recurring_versions WHERE item_id = %s ORDER BY revision", (item,)
    ).fetchall()


def _shares_of(owner_conn: Conn, version: UUID) -> dict[UUID, Decimal]:
    rows = owner_conn.execute(
        "SELECT vehicle_id, amount FROM setup.recurring_allocations WHERE version_id = %s",
        (version,),
    ).fetchall()
    return {UUID(str(r["vehicle_id"])): r["amount"] for r in rows}


def _stopped_from(owner_conn: Conn, item: UUID) -> date | None:
    row = owner_conn.execute(
        "SELECT stopped_from FROM setup.recurring_items WHERE id = %s", (item,)
    ).fetchone()
    assert row is not None
    return row["stopped_from"]  # type: ignore[no-any-return]


def _scoped(
    operator_conn: Conn, owner_conn: Conn, rules: Rules, *grants: str, slot: int = 3
) -> Member:
    """A person with the given grants who reaches North Star only."""
    who = provision_member(operator_conn, slot, "Revenue clerk", "Sam", f"Scoped{slot}")
    for grant in grants:
        set_override(owner_conn, who, grant)
    set_scope(owner_conn, who, who.org, companies=[rules.north])
    return who


def _running(owner_conn: Conn, rules: Rules, **fields: Any) -> UUID:
    """A weekly Parking cost on KDA 482M that started on 2026-03-01 (running)."""
    version = Version(
        effective_from=date(2026, 3, 1),
        shares=fields.pop("shares", {rules.kda: 1200}),
        name="Parking",
        frequency=2,
        day=6,
        expense_item_id=rules.parking,
        bucket=2,
        **fields,
    )
    item, _ = add_schedule(owner_conn, rules.owner.org, version, stopped_from=None)
    return item


# --- what a save writes ---------------------------------------------------------------


def test_a_cost_is_named_after_its_expense_item_and_counts_in_its_bucket(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    org = rules.owner.org
    before = settings_version(owner_conn, org)
    item = _create(
        app_conn, rules.owner, _cost(rules, note="  Stage fees  ", start=date(2026, 3, 1))
    )
    (version,) = _versions(owner_conn, item)
    assert (version["revision"], version["name"], version["kind"], version["bucket"]) == (
        1,
        "Parking",
        1,
        2,
    )
    assert (version["effective_from"], version["start_on"], version["note"]) == (
        date(2026, 3, 1),
        date(2026, 3, 1),
        "Stage fees",
    )
    assert _shares_of(owner_conn, version["id"]) == {rules.kda: Decimal("1200.00")}
    (log,) = change_rows(owner_conn, org, "recurring")
    assert (log["entity_id"], log["vehicle_id"], log["version"]) == (item, None, before + 1)
    assert (log["reason"], log["before"]) == ("Scheduled expense, Parking", "null")
    assert log["after"] == (
        f'{{"Id":"{item}","StoppedFrom":null,"Versions":[{{"Id":"{version["id"]}","Revision":1,'
        '"EffectiveFrom":"2026-03-01","Name":"Parking","Kind":1,"Amount":1200,"Frequency":2,'
        '"Day":6,"LastDay":false,"Month":null,"Start":"2026-03-01","End":null,'
        f'"ExpenseItemId":"{rules.parking}","Bucket":2,"Note":"Stage fees",'
        f'"Allocations":[{{"VehicleId":"{rules.kda}","Amount":1200}}]}}]}}'
    )


def test_a_saving_keeps_its_typed_name_and_a_typed_reason_follows(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    item = _create(
        app_conn,
        rules.owner,
        _saving(rules, name=" Owner savings ", reason="Put money aside for the owner."),
    )
    (version,) = _versions(owner_conn, item)
    assert (version["name"], version["kind"], version["bucket"], version["expense_item_id"]) == (
        "Owner savings",
        2,
        None,
        None,
    )
    assert reasons(owner_conn, rules.owner.org, "recurring") == [
        "Saving, Owner savings. Reason: Put money aside for the owner."
    ]


def test_a_200_character_note_is_accepted(app_conn: Conn, owner_conn: Conn, rules: Rules) -> None:
    item = _create(
        app_conn, rules.owner, _cost(rules, expense_item_id=rules.spares, note="n" * 200)
    )
    (version,) = _versions(owner_conn, item)
    assert (version["name"], version["bucket"], len(version["note"])) == ("Spares", 1, 200)


# --- step 1: the typed reason ---------------------------------------------------------


def test_a_typed_reason_over_500_characters_is_refused(app_conn: Conn, rules: Rules) -> None:
    _create_refused(
        app_conn, rules.owner, _saving(rules, reason="x" * 501), "XC422", "reason_length"
    )


# --- step 2: the expense item ---------------------------------------------------------


def test_a_saving_must_not_name_an_expense_item(app_conn: Conn, rules: Rules) -> None:
    _create_refused(
        app_conn,
        rules.owner,
        _saving(rules, expense_item_id=rules.parking),
        "XC422",
        "recurring_savings_item",
    )


def test_a_cost_needs_an_expense_item_in_use_in_a_category_in_use(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    owner_conn.execute(
        "UPDATE setup.expense_items SET stopped_on = %s WHERE id = %s", (TODAY, rules.towing)
    )
    owner_conn.execute(
        "UPDATE setup.expense_categories SET stopped_on = %s WHERE id = %s",
        (date(2026, 3, 1), rules.loans),
    )
    owner_conn.execute(
        "UPDATE setup.expense_items SET stopped_on = %s WHERE id = %s",
        (date(2026, 3, 16), rules.spares),
    )
    for item in (UUID(int=1), rules.towing, rules.repayment):
        _create_refused(
            app_conn,
            rules.owner,
            _cost(rules, expense_item_id=item),
            "XC422",
            "recurring_item_not_in_use",
        )
    _create(app_conn, rules.owner, _cost(rules, expense_item_id=rules.spares))


# --- step 3: the schedule -------------------------------------------------------------


@pytest.mark.parametrize(
    ("frequency", "day", "last_day", "month"),
    [
        (2, 7, False, None),
        (4, 10, False, None),
        (4, 10, False, 13),
        (4, 29, False, 3),
        (3, 10, False, 3),
        (9, 1, False, None),
    ],
)
def test_a_schedule_of_the_wrong_shape_is_refused(
    app_conn: Conn, rules: Rules, frequency: int, day: int, last_day: bool, month: int | None
) -> None:
    definition = _cost(rules, frequency=frequency, day=day, last_day=last_day, month=month)
    _create_refused(app_conn, rules.owner, definition, "XC422", "recurring_schedule_shape")


def test_yearly_items_save_their_month_and_day(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    on_day = _create(app_conn, rules.owner, _cost(rules, frequency=4, day=10, month=3))
    last_day = _create(
        app_conn, rules.owner, _cost(rules, frequency=4, day=None, last_day=True, month=2)
    )
    assert [
        (v["frequency"], v["month"], v["day"], v["last_day"]) for v in _versions(owner_conn, on_day)
    ] == [(4, 3, 10, False)]
    assert [
        (v["frequency"], v["month"], v["day"], v["last_day"])
        for v in _versions(owner_conn, last_day)
    ] == [(4, 2, None, True)]


# --- step 4: the item -----------------------------------------------------------------


def test_revising_an_unknown_or_invisible_item_is_not_found(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, rules: Rules
) -> None:
    _revise_refused(app_conn, rules.owner, UUID(int=1), _saving(rules), "XC404", "not_found")
    hidden, _ = add_schedule(
        owner_conn, rules.owner.org, Version(date(2026, 3, 1), {rules.kdc: 100})
    )
    scoped = _scoped(operator_conn, owner_conn, rules, *COSTS, *SAVINGS)
    _revise_refused(app_conn, scoped, hidden, _saving(rules), "XC404", "not_found")


# --- step 5: the definition -----------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"name": "  "}, "recurring_name_length"),
        ({"name": "x" * 161}, "recurring_name_length"),
        ({"amount": 0}, "money_invalid"),
        ({"kind": 3}, "recurring_kind_invalid"),
        ({"note": "n" * 201}, "recurring_note_length"),
        ({"end": date(2026, 3, 14)}, "recurring_end_before_start"),
    ],
)
def test_the_definition_is_checked(
    app_conn: Conn, rules: Rules, changes: dict[str, Any], code: str
) -> None:
    _create_refused(app_conn, rules.owner, _saving(rules, **changes), "XC422", code)


def test_shares_are_1_to_500_distinct_vehicles_whose_amounts_add_up(
    app_conn: Conn, rules: Rules
) -> None:
    for allocations in (
        shares(),
        shares((rules.kda, 500), (rules.kda, 500)),
        shares((UUID(int=0), 1000)),
    ):
        _create_refused(
            app_conn,
            rules.owner,
            _saving(rules, allocations=allocations),
            "XC422",
            "recurring_allocations_count",
        )
    _create_refused(
        app_conn,
        rules.owner,
        _saving(rules, allocations=shares((rules.kda, 0), (rules.kdb, 1000))),
        "XC422",
        "money_invalid",
    )
    _create_refused(
        app_conn,
        rules.owner,
        _saving(rules, allocations=shares((rules.kda, 600), (rules.kdb, 300))),
        "XC422",
        "recurring_allocation_sum",
    )


# --- step 6: what new saves may be ----------------------------------------------------


def test_daily_schedules_are_no_longer_offered(app_conn: Conn, rules: Rules) -> None:
    _create_refused(
        app_conn,
        rules.owner,
        _cost(rules, frequency=1, day=None),
        "XC422",
        "recurring_daily_retired",
    )


def test_savings_are_weekly_or_monthly(app_conn: Conn, rules: Rules) -> None:
    _create_refused(
        app_conn,
        rules.owner,
        _saving(rules, frequency=4, day=10, month=3),
        "XC422",
        "recurring_savings_frequency",
    )
    _create(app_conn, rules.owner, _saving(rules, frequency=2, day=6))
    _create(app_conn, rules.owner, _saving(rules, frequency=3, day=None, last_day=True))


def test_a_cost_needs_an_expense_item(app_conn: Conn, rules: Rules) -> None:
    _create_refused(
        app_conn,
        rules.owner,
        _cost(rules, expense_item_id=None),
        "XC422",
        "recurring_cost_needs_item",
    )


def test_a_start_date_is_required(app_conn: Conn, rules: Rules) -> None:
    _create_refused(
        app_conn, rules.owner, _saving(rules, start=None), "XC422", "recurring_start_required"
    )


def test_schedules_start_no_earlier_than_the_first_of_the_business_month(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    _create_refused(
        app_conn,
        rules.owner,
        _saving(rules, start=date(2026, 2, 28)),
        "XC422",
        "recurring_start_too_early",
    )
    _create(app_conn, rules.owner, _saving(rules, start=date(2026, 3, 1)))
    pending = _create(app_conn, rules.owner, _saving(rules, start=date(2026, 3, 20)))
    _revise_refused(
        app_conn,
        rules.owner,
        pending,
        _saving(rules, start=date(2026, 2, 20)),
        "XC422",
        "recurring_start_too_early",
    )
    assert (
        _revise(app_conn, rules.owner, pending, _saving(rules, start=date(2026, 3, 2)))["outcome"]
        == "updated"
    )


def test_an_older_start_is_waived_when_it_is_the_items_own(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    item, _ = add_schedule(
        owner_conn,
        rules.owner.org,
        Version(
            date(2026, 2, 1), {rules.kda: 1000}, name="Owner savings", kind=2, frequency=2, day=5
        ),
    )
    result = _revise(app_conn, rules.owner, item, _saving(rules, start=date(2026, 2, 1), day=6))
    assert result["outcome"] == "updated"


# --- step 7: the shares ---------------------------------------------------------------


def test_every_share_needs_a_vehicle_in_reach(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, rules: Rules
) -> None:
    _create_refused(
        app_conn,
        rules.owner,
        _saving(rules, allocations=shares((UUID(int=5), 1000))),
        "XC404",
        "not_found",
    )
    scoped = _scoped(operator_conn, owner_conn, rules, *COSTS, *SAVINGS)
    _create_refused(
        app_conn,
        scoped,
        _saving(rules, allocations=shares((rules.kda, 500), (rules.kdc, 500))),
        "XC404",
        "not_found",
    )
    _create(
        app_conn, scoped, _saving(rules, allocations=shares((rules.kda, 500), (rules.kdb, 500)))
    )


def test_a_new_share_needs_a_vehicle_in_the_fleet_and_a_company_in_use(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    org = rules.owner.org
    retired = add_vehicle(owner_conn, org, rules.north, "KDE 400D", left_on=TODAY)
    later = add_vehicle(owner_conn, org, rules.north, "KDF 500E", joined_on=date(2026, 3, 20))
    archived = add_company(owner_conn, org, "Old Line", archived_on=date(2026, 3, 10))
    orphan = add_vehicle(owner_conn, org, archived, "KDG 600F")
    for vehicle in (retired, later, orphan):
        _create_refused(
            app_conn,
            rules.owner,
            _saving(rules, allocations=shares((vehicle, 1000))),
            "XC422",
            "recurring_share_inactive",
        )


def test_the_first_bad_share_decides(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, rules: Rules
) -> None:
    retired = add_vehicle(owner_conn, rules.owner.org, rules.north, "KDE 400D", left_on=TODAY)
    scoped = _scoped(operator_conn, owner_conn, rules, *COSTS, *SAVINGS)
    _create_refused(
        app_conn,
        scoped,
        _saving(rules, allocations=shares((retired, 500), (rules.kdc, 500))),
        "XC422",
        "recurring_share_inactive",
    )
    _create_refused(
        app_conn,
        scoped,
        _saving(rules, allocations=shares((rules.kda, 500), (rules.kdc, 500))),
        "XC404",
        "not_found",
    )


def test_a_vehicle_already_on_the_item_may_stay_after_it_retired(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    item = _create(
        app_conn,
        rules.owner,
        _saving(rules, allocations=shares((rules.kda, 700), (rules.kdb, 300))),
    )
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s", (TODAY, rules.kdb)
    )
    revised = _saving(rules, amount=1100, allocations=shares((rules.kda, 800), (rules.kdb, 300)))
    assert _revise(app_conn, rules.owner, item, revised)["outcome"] == "updated"
    _create_refused(
        app_conn,
        rules.owner,
        _saving(rules, allocations=shares((rules.kdb, 1000))),
        "XC422",
        "recurring_share_inactive",
    )


# --- step 8: reach of the current version and the unchanged revise ---------------------


def test_revising_stopping_or_cancelling_needs_every_current_share_in_reach(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, rules: Rules
) -> None:
    item, _ = add_schedule(
        owner_conn,
        rules.owner.org,
        Version(date(2026, 3, 1), {rules.kda: 500, rules.kdc: 700}, kind=2),
    )
    scoped = _scoped(operator_conn, owner_conn, rules, *COSTS, *SAVINGS)
    _revise_refused(
        app_conn,
        scoped,
        item,
        _saving(rules, allocations=shares((rules.kda, 1000))),
        "XC403",
        "permission_missing",
    )
    refuses(
        app_conn,
        "setup_recurring_stop",
        scoped,
        [item, True, "Ended"],
        "XC403",
        "permission_missing",
    )
    refuses(app_conn, "setup_recurring_cancel_stop", scoped, [item], "XC403", "permission_missing")


def test_a_revise_that_changes_nothing_is_unchanged_and_logs_nothing(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    definition = _cost(
        rules, note="Stage fees", allocations=shares((rules.kda, 700), (rules.kdb, 500))
    )
    item = _create(app_conn, rules.owner, definition)
    version = settings_version(owner_conn, rules.owner.org)
    again = replace(
        definition,
        name="Ignored for costs",
        note=" Stage fees ",
        allocations=shares((rules.kdb, Decimal("500.00")), (rules.kda, 700)),
    )
    result = _revise(app_conn, rules.owner, item, again)
    assert (result["outcome"], result["version"]) == ("unchanged", version)
    assert len(_versions(owner_conn, item)) == 1
    assert reasons(owner_conn, rules.owner.org, "recurring") == ["Scheduled expense, Parking"]


# --- step 9: stopped items and running items ------------------------------------------


def test_a_stopped_item_cannot_be_edited_and_a_later_stop_stays(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    item = _create(app_conn, rules.owner, _saving(rules))
    run(app_conn, "setup_recurring_stop", rules.owner, item, True, "Ended")
    _revise_refused(
        app_conn,
        rules.owner,
        item,
        _saving(rules, amount=900, allocations=shares((rules.kda, 900))),
        "XC422",
        "recurring_stopped_edit",
    )
    later = _create(app_conn, rules.owner, _saving(rules))
    owner_conn.execute(
        "UPDATE setup.recurring_items SET stopped_from = %s WHERE id = %s",
        (date(2026, 3, 18), later),
    )
    assert _revise(app_conn, rules.owner, later, _saving(rules, day=6))["outcome"] == "updated"
    assert _stopped_from(owner_conn, later) == date(2026, 3, 18)
    assert [v["revision"] for v in _versions(owner_conn, later)] == [1, 2]


def test_a_running_item_keeps_its_start_date(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    item = _running(owner_conn, rules)
    _revise_refused(
        app_conn,
        rules.owner,
        item,
        _cost(rules, start=date(2026, 3, 20)),
        "XC422",
        "recurring_running_start_change",
    )
    result = _revise(app_conn, rules.owner, item, _cost(rules, start=date(2026, 3, 1), day=0))
    assert result["outcome"] == "updated"
    second = _versions(owner_conn, item)[1]
    assert (second["revision"], second["effective_from"], second["start_on"], second["day"]) == (
        2,
        TODAY,
        date(2026, 3, 1),
        0,
    )


# --- dated revisions ------------------------------------------------------------------


def test_postponing_a_pending_item_takes_effect_today_and_backdating_from_its_start(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    pending = _create(app_conn, rules.owner, _saving(rules, start=date(2026, 3, 20)))
    assert _versions(owner_conn, pending)[0]["effective_from"] == date(2026, 3, 20)
    _revise(app_conn, rules.owner, pending, _saving(rules, start=date(2026, 3, 25)))
    _revise(app_conn, rules.owner, pending, _saving(rules, start=date(2026, 3, 10)))
    versions = _versions(owner_conn, pending)
    assert [(v["revision"], v["effective_from"], v["start_on"]) for v in versions] == [
        (1, date(2026, 3, 20), date(2026, 3, 20)),
        (2, TODAY, date(2026, 3, 25)),
        (3, date(2026, 3, 10), date(2026, 3, 10)),
    ]


# --- the change sentences -------------------------------------------------------------


def test_every_revise_names_the_kind_and_the_item_as_it_ends(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    base = _cost(rules, allocations=shares((rules.kda, 1200)))
    item = _create(app_conn, rules.owner, base)
    one = replace(base, note="Stage fees")
    _revise(app_conn, rules.owner, item, one)
    two = replace(one, amount=1500, allocations=shares((rules.kda, 1000), (rules.kdb, 500)))
    _revise(app_conn, rules.owner, item, two)
    three = replace(two, day=None, frequency=3, last_day=True, end=date(2026, 12, 31), note=None)
    _revise(
        app_conn,
        rules.owner,
        item,
        three,
    )
    switch = replace(three, kind=2, expense_item_id=None, name="Parking", reason="Now a saving")
    _revise(app_conn, rules.owner, item, switch)
    rename = replace(switch, name="Parking fund", reason=None)
    _revise(app_conn, rules.owner, item, rename)
    assert reasons(owner_conn, rules.owner.org, "recurring") == [
        "Scheduled expense, Parking",
        "Scheduled expense, Parking",
        "Scheduled expense, Parking",
        "Scheduled expense, Parking",
        "Saving, Parking. Reason: Now a saving.",
        "Saving, Parking fund",
    ]
    log = change_rows(owner_conn, rules.owner.org, "recurring")[2]
    before, after = json.loads(log["before"]), json.loads(log["after"])
    assert [v["Revision"] for v in before["Versions"]] == [1, 2]
    assert [v["Revision"] for v in after["Versions"]] == [1, 2, 3]
    assert after["Versions"][2]["Allocations"] == sorted(
        [
            {"VehicleId": str(rules.kda), "Amount": 1000},
            {"VehicleId": str(rules.kdb), "Amount": 500},
        ],
        key=lambda a: str(a["VehicleId"]),
    )


def test_a_new_bucket_or_expense_item_is_a_revision_named_after_the_item(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    item = _create(app_conn, rules.owner, _cost(rules))
    owner_conn.execute(
        "UPDATE setup.expense_categories SET bucket = 1 WHERE id = %s", (rules.charges,)
    )
    _revise(app_conn, rules.owner, item, _cost(rules))
    _revise(app_conn, rules.owner, item, _cost(rules, expense_item_id=rules.repayment))
    assert [v["bucket"] for v in _versions(owner_conn, item)] == [2, 1, 3]
    assert reasons(owner_conn, rules.owner.org, "recurring")[1:] == [
        "Scheduled expense, Parking",
        "Scheduled expense, Loan repayment",
    ]


# --- stop and cancel the stop ---------------------------------------------------------


def test_stopping_needs_a_typed_reason_and_a_confirmation_before_anything_else(
    app_conn: Conn, rules: Rules
) -> None:
    for reason in (None, "", "  ", "x" * 501):
        refuses(
            app_conn,
            "setup_recurring_stop",
            rules.owner,
            [UUID(int=1), True, reason],
            "XC422",
            "reason_length",
        )
    for confirmed in (False, None):
        refuses(
            app_conn,
            "setup_recurring_stop",
            rules.owner,
            [UUID(int=1), confirmed, "Ended"],
            "XC422",
            "recurring_stop_confirm",
        )
    refuses(
        app_conn,
        "setup_recurring_stop",
        rules.owner,
        [UUID(int=1), True, "Ended"],
        "XC404",
        "not_found",
    )


def test_a_stop_takes_effect_today_and_repeating_it_is_unchanged(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    item = _create(app_conn, rules.owner, _cost(rules))
    result = run(
        app_conn,
        "setup_recurring_stop",
        rules.owner,
        item,
        True,
        "Parking moved into the SACCO fee",
    )
    assert result["outcome"] == "updated"
    assert _stopped_from(owner_conn, item) == TODAY
    assert (
        run(app_conn, "setup_recurring_stop", rules.owner, item, True, "Again")["outcome"]
        == "unchanged"
    )
    assert reasons(owner_conn, rules.owner.org, "recurring")[-1] == (
        "Scheduled expense, Parking. Reason: Parking moved into the SACCO fee."
    )
    assert json.loads(change_rows(owner_conn, rules.owner.org, "recurring")[-1]["after"])[
        "StoppedFrom"
    ] == ("2026-03-15")


@pytest.mark.parametrize(
    ("stopped_from", "code"),
    [
        (date(2026, 3, 18), "recurring_stop_later_pending"),
        (date(2026, 3, 12), "recurring_already_stopped"),
    ],
)
def test_a_stop_on_another_date_is_never_re_dated(
    app_conn: Conn, owner_conn: Conn, rules: Rules, stopped_from: date, code: str
) -> None:
    item = _create(app_conn, rules.owner, _cost(rules))
    owner_conn.execute(
        "UPDATE setup.recurring_items SET stopped_from = %s WHERE id = %s", (stopped_from, item)
    )
    refuses(app_conn, "setup_recurring_stop", rules.owner, [item, True, "Ended"], "XC422", code)


def test_cancelling_a_later_stop_and_the_states_it_refuses(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    item = _create(app_conn, rules.owner, _cost(rules))
    assert run(app_conn, "setup_recurring_cancel_stop", rules.owner, item)["outcome"] == "unchanged"
    owner_conn.execute(
        "UPDATE setup.recurring_items SET stopped_from = %s WHERE id = %s",
        (date(2026, 3, 18), item),
    )
    assert run(app_conn, "setup_recurring_cancel_stop", rules.owner, item)["outcome"] == "updated"
    assert _stopped_from(owner_conn, item) is None
    assert reasons(owner_conn, rules.owner.org, "recurring")[-1] == "Scheduled expense, Parking"
    run(app_conn, "setup_recurring_stop", rules.owner, item, True, "Ended")
    refuses(
        app_conn,
        "setup_recurring_cancel_stop",
        rules.owner,
        [item],
        "XC422",
        "recurring_stop_in_effect",
    )
    refuses(
        app_conn, "setup_recurring_cancel_stop", rules.owner, [UUID(int=1)], "XC404", "not_found"
    )


# --- the list -------------------------------------------------------------------------


def test_a_scoped_viewer_sees_only_its_shares_and_that_the_item_reaches_further(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, rules: Rules
) -> None:
    org = rules.owner.org
    shared, _ = add_schedule(
        owner_conn,
        org,
        Version(date(2026, 3, 1), {rules.kda: 500, rules.kdc: 700}, name="Office rent", kind=2),
    )
    own, _ = add_schedule(
        owner_conn, org, Version(date(2026, 3, 1), {rules.kdb: 300}, name="Insurance", kind=2)
    )
    add_schedule(
        owner_conn, org, Version(date(2026, 3, 1), {rules.kdc: 900}, name="Hidden", kind=2)
    )
    scoped = _scoped(operator_conn, owner_conn, rules, "scheduled.view", "savings.view")
    page = read(app_conn, "setup_recurring_list", scoped, 1, 25, None, None, None)
    assert page["total"] == 2
    insurance, rent = page["items"]
    assert (insurance["id"], insurance["partial"], insurance["amount"]) == (str(own), False, 300)
    assert (rent["id"], rent["partial"], rent["amount"], rent["active_amount"]) == (
        str(shared),
        True,
        500,
        500,
    )
    assert rent["allocations"] == [
        {"vehicle_id": str(rules.kda), "amount": 500, "registration": "KDA 482M", "active": True}
    ]
    owner_page = read(app_conn, "setup_recurring_list", rules.owner, 1, 1, None, None, None)
    assert (owner_page["total"], owner_page["items"][0]["name"]) == (3, "Hidden")
    second = read(app_conn, "setup_recurring_list", rules.owner, 3, 1, None, None, None)["items"][0]
    assert (second["name"], second["partial"], second["amount"]) == ("Office rent", False, 1200)


def test_retired_shares_stay_in_the_total_and_active_amount_says_what_still_posts(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    later = add_vehicle(
        owner_conn, rules.owner.org, rules.north, "KDF 500E", joined_on=date(2026, 3, 20)
    )
    item, _ = add_schedule(
        owner_conn,
        rules.owner.org,
        Version(date(2026, 3, 1), {rules.kda: 600, rules.kdb: 300, later: 100}),
    )
    row = read(app_conn, "setup_recurring_list", rules.owner, 1, 25, None, None, None)["items"][0]
    assert (row["amount"], row["active_amount"]) == (1000, 900)
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s", (TODAY, rules.kdb)
    )
    row = read(app_conn, "setup_recurring_list", rules.owner, 1, 25, None, None, None)["items"][0]
    assert (row["amount"], row["active_amount"]) == (1000, 600)
    assert [(a["registration"], a["active"]) for a in row["allocations"]] == [
        ("KDA 482M", True),
        ("KDB 111A", False),
        ("KDF 500E", False),
    ]
    assert row["id"] == str(item)


def test_the_list_row_is_the_latest_version_with_its_reported_bucket(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    item, (_, latest) = add_schedule(
        owner_conn,
        rules.owner.org,
        Version(date(2026, 2, 1), {rules.kda: 100}, name="Old", bucket=1),
        Version(
            date(2026, 3, 1),
            {rules.kda: 250},
            name="Fuel",
            expense_item_id=rules.parking,
            frequency=2,
            day=3,
            note="Legacy",
            start_on=date(2026, 2, 1),
        ),
    )
    saving = _create(app_conn, rules.owner, _saving(rules))
    rows = {
        r["id"]: r
        for r in read(app_conn, "setup_recurring_list", rules.owner, 1, 25, None, None, None)[
            "items"
        ]
    }
    cost = rows[str(item)]
    assert cost == {
        "id": str(item),
        "version_id": str(latest),
        "revision": 2,
        "name": "Fuel",
        "kind": 1,
        "amount": 250,
        "frequency": 2,
        "day": 3,
        "last_day": False,
        "start_on": "2026-02-01",
        "end_on": None,
        "stopped_from": None,
        "allocations": [
            {
                "vehicle_id": str(rules.kda),
                "amount": 250,
                "registration": "KDA 482M",
                "active": True,
            }
        ],
        "partial": False,
        "expense_item_id": str(rules.parking),
        "expense_item_name": "Parking",
        "bucket": 2,
        "note": "Legacy",
        "month": None,
        "active_amount": 250,
    }
    assert (rows[str(saving)]["bucket"], rows[str(saving)]["expense_item_name"]) == (None, None)


def test_the_list_needs_commitments_view_and_a_page_in_range(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    refuses(
        app_conn,
        "setup_recurring_list",
        rules.clerk,
        [1, 25, None, None, None],
        "XC403",
        "permission_missing",
    )
    refuses(
        app_conn,
        "setup_recurring_list",
        rules.owner,
        [1, 101, None, None, None],
        "XC422",
        "page_out_of_range",
    )
    for routine, args in [
        ("setup_recurring_create", _saving(rules).args()),
        ("setup_recurring_stop", [UUID(int=1), True, "Ended"]),
        ("setup_recurring_cancel_stop", [UUID(int=1)]),
        ("setup_vehicle_options", []),
    ]:
        refuses(app_conn, routine, rules.clerk, args, "XC403", "permission_missing")
    other = seed_organization(owner_conn)
    refused(
        app_conn,
        "setup_recurring_list",
        [other.user, rules.owner.org, REQUEST, 1, 25, None, None, None, T0],
        "XC403",
        "not_member",
    )


def _ids(app: Conn, who: Member, *filters: Any, page: int = 1, size: int = 25) -> list[str]:
    return [r["id"] for r in read(app, "setup_recurring_list", who, page, size, *filters)["items"]]


def test_the_list_filters_by_kind_company_and_status_with_running_items_first(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    org = rules.owner.org
    gone = add_vehicle(owner_conn, org, rules.north, "KDE 300C", left_on=TODAY)
    coming = add_vehicle(owner_conn, org, rules.south, "KDF 400D", joined_on=date(2026, 3, 20))
    start = date(2026, 3, 1)
    parked, _ = add_schedule(owner_conn, org, Version(start, {rules.kda: 500}, name="Parking"))
    ended, _ = add_schedule(
        owner_conn,
        org,
        Version(start, {rules.kdb: 300}, name="Annual fee", end_on=date(2026, 3, 14)),
    )
    left, _ = add_schedule(owner_conn, org, Version(start, {gone: 200}, name="Bodywork"))
    saving, _ = add_schedule(
        owner_conn, org, Version(start, {rules.kdc: 500}, name="Filter savings", kind=2)
    )
    cleaning, _ = add_schedule(
        owner_conn, org, Version(start, {rules.kdc: 500}, name="Cleaning"), stopped_from=TODAY
    )
    alarm, _ = add_schedule(owner_conn, org, Version(start, {coming: 100}, name="Alarm"))
    owner = rules.owner
    everything = [saving, parked, alarm, ended, left, cleaning]
    assert _ids(app_conn, owner, None, None, None) == [str(i) for i in everything]
    assert _ids(app_conn, owner, "all", None, "") == [str(i) for i in everything]
    assert _ids(app_conn, owner, None, rules.north, None) == [str(parked), str(ended), str(left)]
    assert _ids(app_conn, owner, None, rules.south, None) == [
        str(saving),
        str(alarm),
        str(cleaning),
    ]
    assert _ids(app_conn, owner, None, rules.south, "running") == [str(saving)]
    assert _ids(app_conn, owner, None, rules.south, "stopped") == [str(alarm), str(cleaning)]
    assert _ids(app_conn, owner, "cost", rules.south, None) == [str(alarm), str(cleaning)]
    assert _ids(app_conn, owner, "savings", rules.south, None) == [str(saving)]
    assert _ids(app_conn, owner, "", None, "running") == [str(saving), str(parked)]
    assert _ids(app_conn, owner, None, UUID(int=7), None) == []
    page = read(app_conn, "setup_recurring_list", owner, 2, 1, None, rules.south, None)
    assert (page["total"], [r["id"] for r in page["items"]]) == (3, [str(alarm)])


def test_the_company_filter_and_running_read_only_the_vehicles_in_reach(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, rules: Rules
) -> None:
    org = rules.owner.org
    gone = add_vehicle(owner_conn, org, rules.north, "KDE 300C", left_on=TODAY)
    shared, _ = add_schedule(
        owner_conn, org, Version(date(2026, 3, 1), {gone: 200, rules.kdc: 300}, name="Shared")
    )
    scoped = _scoped(operator_conn, owner_conn, rules, "scheduled.view", "savings.view")
    assert _ids(app_conn, rules.owner, None, rules.south, "running") == [str(shared)]
    assert _ids(app_conn, scoped, None, rules.south, None) == []
    assert _ids(app_conn, scoped, None, rules.north, None) == [str(shared)]
    assert _ids(app_conn, scoped, None, None, "running") == []
    assert _ids(app_conn, scoped, None, None, "stopped") == [str(shared)]


def test_a_filter_outside_its_choices_is_refused_before_membership_and_the_page(
    app_conn: Conn, owner_conn: Conn, rules: Rules
) -> None:
    owner, clerk = rules.owner, rules.clerk
    kind, status = "recurring_filter_kind_invalid", "recurring_filter_status_invalid"
    for value in ("fuel", "Cost", " cost"):
        refuses(app_conn, "setup_recurring_list", owner, [1, 25, value, None, None], "XC422", kind)
    for value in ("paused", "Running"):
        refuses(
            app_conn, "setup_recurring_list", owner, [1, 25, None, None, value], "XC422", status
        )
    refuses(app_conn, "setup_recurring_list", owner, [1, 25, "fuel", None, "paused"], "XC422", kind)
    refuses(app_conn, "setup_recurring_list", owner, [0, 25, None, None, "paused"], "XC422", status)
    refuses(app_conn, "setup_recurring_list", clerk, [1, 25, "fuel", None, None], "XC422", kind)
    other = seed_organization(owner_conn)
    refused(
        app_conn,
        "setup_recurring_list",
        [other.user, owner.org, REQUEST, 1, 25, None, None, "paused", T0],
        "XC422",
        status,
    )


# --- vehicle options ------------------------------------------------------------------


def test_the_picker_offers_only_vehicles_a_new_share_can_use(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, rules: Rules
) -> None:
    org = rules.owner.org
    add_vehicle(owner_conn, org, rules.north, "KDE 400D", left_on=TODAY)
    add_vehicle(owner_conn, org, rules.north, "KDF 500E", joined_on=date(2026, 3, 20))
    leaving = add_vehicle(
        owner_conn, org, rules.north, "KDH 700G", left_on=date(2026, 3, 16), fleet_number="N-7"
    )
    archived = add_company(owner_conn, org, "Old Line", archived_on=date(2026, 3, 10))
    add_vehicle(owner_conn, org, archived, "KDG 600F")
    options = read(app_conn, "setup_vehicle_options", rules.owner)
    assert [(o["registration"], o["company_name"], o["active"]) for o in options] == [
        ("KDA 482M", "North Star", True),
        ("KDB 111A", "North Star", True),
        ("KDC 200B", "South Line", True),
        ("KDH 700G", "North Star", True),
    ]
    assert options[3] == {
        "id": str(leaving),
        "company_id": str(rules.north),
        "company_name": "North Star",
        "registration": "KDH 700G",
        "fleet_number": "N-7",
        "active": True,
    }
    scoped = _scoped(operator_conn, owner_conn, rules, *COSTS, *SAVINGS)
    assert [o["registration"] for o in read(app_conn, "setup_vehicle_options", scoped)] == [
        "KDA 482M",
        "KDB 111A",
        "KDH 700G",
    ]


# --- each kind has its own rights -----------------------------------------------------


def test_the_rights_of_one_kind_reach_no_item_of_the_other(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, rules: Rules
) -> None:
    org = rules.owner.org
    cost, _ = add_schedule(owner_conn, org, Version(date(2026, 3, 1), {rules.kda: 100}))
    saving, _ = add_schedule(
        owner_conn, org, Version(date(2026, 3, 1), {rules.kda: 100}, name="Owner savings", kind=2)
    )
    started = date(2026, 3, 1)
    for grants, slot, mine, other, own_definition, other_definition in [
        (COSTS, 3, cost, saving, _cost(rules, start=started), _saving(rules)),
        (SAVINGS, 4, saving, cost, _saving(rules, start=started), _cost(rules)),
    ]:
        who = _scoped(operator_conn, owner_conn, rules, *grants, slot=slot)
        page = read(app_conn, "setup_recurring_list", who, 1, 25, None, None, None)
        assert (page["total"], [i["id"] for i in page["items"]]) == (1, [str(mine)])
        _create_refused(app_conn, who, other_definition, "XC403", "permission_missing")
        _revise_refused(app_conn, who, other, other_definition, "XC404", "not_found")
        refuses(app_conn, "setup_recurring_stop", who, [other, True, "Ended"], "XC404", "not_found")
        refuses(app_conn, "setup_recurring_cancel_stop", who, [other], "XC404", "not_found")
        _revise_refused(app_conn, who, mine, other_definition, "XC403", "permission_missing")
        assert _revise(app_conn, who, mine, own_definition)["outcome"] == "updated"


def test_switching_the_kind_needs_the_edit_right_of_both_kinds(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, rules: Rules
) -> None:
    item = _create(app_conn, rules.owner, _cost(rules))
    both = _scoped(operator_conn, owner_conn, rules, *COSTS, "savings.edit")
    assert _revise(app_conn, both, item, _saving(rules))["outcome"] == "updated"
    assert reasons(owner_conn, rules.owner.org, "recurring")[-1] == "Saving, Owner savings"


def test_viewing_rights_alone_cannot_open_the_vehicle_picker(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, rules: Rules
) -> None:
    viewer = _scoped(operator_conn, owner_conn, rules, "scheduled.view", "savings.view")
    refuses(app_conn, "setup_vehicle_options", viewer, [], "XC403", "permission_missing")
    for slot, right in enumerate(
        ("scheduled.add", "scheduled.edit", "savings.add", "savings.edit")
    ):
        who = _scoped(operator_conn, owner_conn, rules, right, slot=4 + slot)
        assert len(read(app_conn, "setup_vehicle_options", who)) == 2
