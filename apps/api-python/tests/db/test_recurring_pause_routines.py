"""Pause, resume, runs and summary of scheduled items (``api.setup_recurring_pause``,
``_resume``, ``_runs``, ``_summary``), the list's new fields, and the saving model: a saving
starts on the business date with no end, may carry a revenue rule (held until its window is
complete, then saved or skipped for good) and an opening balance.

The business date is Sunday 2026-03-15; items that start earlier are seeded as ``xcode_owner``."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..support.scenario import Conn
from ..support.setup_rows import (
    Definition,
    Version,
    add_away,
    add_category,
    add_item,
    add_record,
    add_schedule,
    change_rows,
    read,
    reasons,
    refuses,
    run,
    shares,
)
from ..support.tenancy import (
    Member,
    add_company,
    add_vehicle,
    provision_member,
    set_organization,
    set_override,
    set_scope,
)

TODAY = date(2026, 3, 15)


def _days(n: int) -> date:
    return TODAY - timedelta(days=n)


@dataclass(frozen=True, slots=True)
class World:
    owner: Member
    clerk: Member
    north: UUID
    south: UUID
    kda: UUID
    kdb: UUID
    kdc: UUID
    parking: UUID


@pytest.fixture
def world(operator_conn: Conn, owner_conn: Conn) -> World:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 2, "Revenue clerk", "Cleo", "Clerk")
    set_organization(owner_conn, owner.org, business_date=TODAY)
    org = owner.org
    north = add_company(owner_conn, org, "North Star")
    south = add_company(owner_conn, org, "South Line")
    charges = add_category(owner_conn, org, "Charges", bucket=2)
    return World(
        owner=owner,
        clerk=clerk,
        north=north,
        south=south,
        kda=add_vehicle(owner_conn, org, north, "KDA 482M"),
        kdb=add_vehicle(owner_conn, org, north, "KDB 111A"),
        kdc=add_vehicle(owner_conn, org, south, "KDC 200B"),
        parking=add_item(owner_conn, org, charges, "Parking"),
    )


def _daily(
    owner_conn: Conn,
    world: World,
    *,
    kind: int = 1,
    since: int = 10,
    on: dict[UUID, int] | None = None,
    name: str = "Insurance",
    stopped_from: date | None = None,
) -> tuple[UUID, UUID]:
    item, versions = add_schedule(
        owner_conn,
        world.owner.org,
        Version(
            effective_from=_days(since),
            shares=on or {world.kda: 500},
            name=name,
            kind=kind,
            frequency=1,
            day=None,
            expense_item_id=world.parking if kind == 1 else None,
            bucket=2 if kind == 1 else None,
        ),
        stopped_from=stopped_from,
    )
    return item, versions[0]


def _rule(owner_conn: Conn, version: UUID, minimum: int, days: int) -> None:
    owner_conn.execute(
        "UPDATE setup.recurring_versions SET condition_min = %s, condition_days = %s WHERE id = %s",
        (minimum, days, version),
    )


def _capture(
    app: Conn, who: Member, vehicle: UUID, day: date, amount: int, version: int | None = None
) -> dict[str, Any]:
    return run(app, "revenue_capture", who, vehicle, day, amount, None, None, version, None)


def _runs(app: Conn, who: Member, item: UUID) -> dict[str, Any]:
    result: dict[str, Any] = read(app, "setup_recurring_runs", who, item)
    return result


def _shares(app: Conn, who: Member, item: UUID) -> dict[str, list[tuple[str, str, Any]]]:
    return {
        r["date"]: [(s["registration"], s["state"], s["revenue"]) for s in r["shares"]]
        for r in _runs(app, who, item)["runs"]
    }


def _pauses(owner_conn: Conn, item: UUID) -> list[tuple[date, date | None]]:
    rows = owner_conn.execute(
        "SELECT paused_from, paused_through FROM setup.recurring_pauses WHERE item_id = %s "
        "ORDER BY paused_from",
        (item,),
    ).fetchall()
    return [(r["paused_from"], r["paused_through"]) for r in rows]


def _decided(owner_conn: Conn, item: UUID) -> list[tuple[date, int, Decimal]]:
    rows = owner_conn.execute(
        "SELECT run_on, state, revenue FROM setup.saving_runs WHERE item_id = %s ORDER BY run_on",
        (item,),
    ).fetchall()
    return [(r["run_on"], r["state"], r["revenue"]) for r in rows]


def _list_item(app: Conn, who: Member, item: UUID) -> dict[str, Any]:
    page = read(app, "setup_recurring_list", who, 1, 100, None, None, None)
    return next(i for i in page["items"] if UUID(i["id"]) == item)


# --- pause and resume -------------------------------------------------------------------


def test_a_pause_starts_today_and_pausing_again_changes_nothing(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    item, _ = _daily(owner_conn, world)
    assert run(app_conn, "setup_recurring_pause", world.owner, item)["outcome"] == "updated"
    assert run(app_conn, "setup_recurring_pause", world.owner, item)["outcome"] == "unchanged"
    assert _pauses(owner_conn, item) == [(TODAY, None)]
    assert reasons(owner_conn, world.owner.org, "recurring") == ["Scheduled expense, Insurance"]


def test_a_paused_day_posts_nothing_and_a_resume_runs_again_from_today(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    item, _ = _daily(owner_conn, world)
    set_organization(owner_conn, world.owner.org, business_date=_days(3))
    run(app_conn, "setup_recurring_pause", world.owner, item)
    set_organization(owner_conn, world.owner.org, business_date=TODAY)
    assert run(app_conn, "setup_recurring_resume", world.owner, item)["outcome"] == "updated"
    assert run(app_conn, "setup_recurring_resume", world.owner, item)["outcome"] == "unchanged"
    assert _pauses(owner_conn, item) == [(_days(3), _days(1))]
    runs = _runs(app_conn, world.owner, item)
    assert [r["date"] for r in runs["runs"]] == [
        str(d) for d in (TODAY, _days(4), _days(5), _days(6), _days(7), _days(8), _days(9))
    ] + [str(_days(10))]
    assert runs["run_count"] == 8
    assert Decimal(str(runs["total"])) == Decimal(4000)


def test_a_resume_on_the_day_of_the_pause_covers_no_day(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    item, _ = _daily(owner_conn, world, since=2)
    run(app_conn, "setup_recurring_pause", world.owner, item)
    run(app_conn, "setup_recurring_resume", world.owner, item)
    assert _pauses(owner_conn, item) == [(TODAY, _days(1))]
    assert [r["date"] for r in _runs(app_conn, world.owner, item)["runs"]] == [
        str(TODAY),
        str(_days(1)),
        str(_days(2)),
    ]


def test_a_stopped_item_refuses_a_pause_and_a_resume_but_not_an_idle_resume(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    stopped, _ = _daily(owner_conn, world, stopped_from=TODAY)
    refuses(
        app_conn,
        "setup_recurring_pause",
        world.owner,
        [stopped],
        "XC422",
        "recurring_already_stopped",
    )
    assert run(app_conn, "setup_recurring_resume", world.owner, stopped)["outcome"] == "unchanged"
    paused, _ = _daily(owner_conn, world, name="Fuel")
    run(app_conn, "setup_recurring_pause", world.owner, paused)
    owner_conn.execute(
        "UPDATE setup.recurring_items SET stopped_from = %s WHERE id = %s", (TODAY, paused)
    )
    refuses(
        app_conn,
        "setup_recurring_resume",
        world.owner,
        [paused],
        "XC422",
        "recurring_already_stopped",
    )
    pending, _ = _daily(owner_conn, world, name="Later", stopped_from=TODAY + timedelta(days=5))
    assert run(app_conn, "setup_recurring_pause", world.owner, pending)["outcome"] == "updated"


def test_the_pause_right_of_the_items_kind_is_needed(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    cost, _ = _daily(owner_conn, world)
    saving, _ = _daily(owner_conn, world, kind=2, name="Owner savings")
    set_scope(owner_conn, world.clerk, world.owner.org, all_companies=True)
    for right in ("scheduled.view", "savings.view"):
        set_override(owner_conn, world.clerk, right)
    refuses(app_conn, "setup_recurring_pause", world.clerk, [cost], "XC403", "permission_missing")
    set_override(owner_conn, world.clerk, "scheduled.pause")
    assert run(app_conn, "setup_recurring_pause", world.clerk, cost)["outcome"] == "updated"
    refuses(app_conn, "setup_recurring_pause", world.clerk, [saving], "XC403", "permission_missing")
    refuses(
        app_conn, "setup_recurring_resume", world.clerk, [saving], "XC403", "permission_missing"
    )
    set_override(owner_conn, world.clerk, "savings.pause")
    assert run(app_conn, "setup_recurring_pause", world.clerk, saving)["outcome"] == "updated"
    assert reasons(owner_conn, world.owner.org, "recurring") == [
        "Scheduled expense, Insurance",
        "Saving, Owner savings",
    ]


def test_a_share_on_a_hidden_vehicle_refuses_the_pause_and_a_hidden_item_is_not_found(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    both, _ = _daily(owner_conn, world, on={world.kda: 300, world.kdc: 200})
    hidden, _ = _daily(owner_conn, world, on={world.kdc: 500}, name="South only")
    set_scope(owner_conn, world.clerk, world.owner.org, companies=[world.north])
    for right in ("scheduled.view", "scheduled.pause"):
        set_override(owner_conn, world.clerk, right)
    refuses(app_conn, "setup_recurring_pause", world.clerk, [both], "XC403", "permission_missing")
    refuses(app_conn, "setup_recurring_pause", world.clerk, [hidden], "XC404", "not_found")
    assert _pauses(owner_conn, both) == []


def test_the_snapshots_carry_the_open_pause_and_every_pause(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    item, _ = _daily(owner_conn, world)
    run(app_conn, "setup_recurring_pause", world.owner, item)
    row = change_rows(owner_conn, world.owner.org, "recurring")[-1]
    before, after = json.loads(row["before"]), json.loads(row["after"])
    assert list(before)[:4] == ["Id", "StoppedFrom", "PausedFrom", "Pauses"]
    assert (before["PausedFrom"], before["Pauses"]) == (None, [])
    assert (after["PausedFrom"], after["Pauses"]) == (
        str(TODAY),
        [{"From": str(TODAY), "Through": None}],
    )
    assert list(after)[-2:] == ["Versions", "Opening"]
    assert list(after["Versions"][0])[-3:] == ["Allocations", "ConditionMin", "ConditionDays"]


# --- runs and the saving rule -------------------------------------------------------------


def test_a_cost_run_posts_and_a_saving_without_a_rule_is_saved_with_no_revenue(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    cost, _ = _daily(owner_conn, world, since=0)
    saving, _ = _daily(owner_conn, world, kind=2, since=0, name="Owner savings")
    assert _shares(app_conn, world.owner, cost) == {str(TODAY): [("KDA 482M", "posted", None)]}
    assert _shares(app_conn, world.owner, saving) == {str(TODAY): [("KDA 482M", "saved", None)]}


def test_a_held_run_is_saved_once_its_day_reaches_the_minimum(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    item, version = _daily(owner_conn, world, kind=2, since=1, name="Owner savings")
    _rule(owner_conn, version, 5000, 1)
    assert _shares(app_conn, world.owner, item) == {
        str(TODAY): [("KDA 482M", "held", 0)],
        str(_days(1)): [("KDA 482M", "held", 0)],
    }
    assert Decimal(str(_runs(app_conn, world.owner, item)["total"])) == 0
    _capture(app_conn, world.owner, world.kda, _days(1), 5000)
    assert _decided(owner_conn, item) == [(_days(1), 1, Decimal("5000.00"))]
    runs = _runs(app_conn, world.owner, item)
    assert _shares(app_conn, world.owner, item)[str(_days(1))] == [("KDA 482M", "saved", 5000)]
    assert Decimal(str(runs["total"])) == Decimal(500)


def test_a_run_below_the_minimum_is_skipped_and_a_later_correction_does_not_flip_it(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    item, version = _daily(owner_conn, world, kind=2, since=0, name="Owner savings")
    _rule(owner_conn, version, 6000, 1)
    saved = _capture(app_conn, world.owner, world.kda, TODAY, 4500)
    _capture(app_conn, world.owner, world.kda, TODAY, 9000, saved["version"])
    assert _decided(owner_conn, item) == [(TODAY, 2, Decimal("4500.00"))]
    assert _shares(app_conn, world.owner, item) == {str(TODAY): [("KDA 482M", "skipped", 4500)]}
    assert Decimal(str(_runs(app_conn, world.owner, item)["total"])) == 0


def test_a_week_window_waits_for_every_active_day_and_leaves_out_days_away(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    item, version = _daily(owner_conn, world, kind=2, since=1, on={world.kdb: 700}, name="Week")
    _rule(owner_conn, version, 15000, 7)
    add_away(owner_conn, world.owner.org, world.kdb, _days(3), _days(1))
    for n in (7, 6, 5):
        add_record(owner_conn, world.owner.org, world.kdb, _days(n), 4000, recorder=world.owner.id)
    assert _decided(owner_conn, item) == []
    _capture(app_conn, world.owner, world.kdb, _days(4), 4000)
    assert _decided(owner_conn, item) == []
    _capture(app_conn, world.owner, world.kdb, _days(1), 4000)
    assert _decided(owner_conn, item) == [(_days(1), 1, Decimal("20000.00"))]
    assert _shares(app_conn, world.owner, item)[str(TODAY)] == [("KDB 111A", "held", 16000)]
    _capture(app_conn, world.owner, world.kdb, TODAY, 4000)
    assert _decided(owner_conn, item)[-1] == (TODAY, 1, Decimal("20000.00"))


def test_two_connections_deciding_one_run_store_one_row(
    app_url: str, owner_conn: Conn, world: World
) -> None:
    item, version = _daily(owner_conn, world, kind=2, since=0, name="Week")
    _rule(owner_conn, version, 1000, 7)
    for n in (6, 5, 4, 3, 2):
        add_record(owner_conn, world.owner.org, world.kda, _days(n), 5000, recorder=world.owner.id)
    first, late = _race(
        app_url,
        lambda conn: _capture(conn, world.owner, world.kda, _days(1), 5000),
        lambda conn: _capture(conn, world.owner, world.kda, TODAY, 5000),
    )
    assert first["outcome"] == "created"
    assert late["outcome"] == "created"
    assert _decided(owner_conn, item) == [(TODAY, 1, Decimal("35000.00"))]


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


# --- the saving save: start, end, rule and opening ----------------------------------------


def _saving(world: World, **changes: Any) -> Definition:
    base = Definition(
        allocations=shares((world.kda, 1000)),
        amount=1000,
        name="Owner savings",
        kind=2,
        frequency=1,
        day=None,
        start=_days(20),
    )
    return replace(base, **changes)


def _create(app: Conn, who: Member, definition: Definition) -> UUID:
    return UUID(str(run(app, "setup_recurring_create", who, *definition.args())["id"]))


def test_a_new_saving_starts_on_the_business_date_and_a_revise_keeps_its_start(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    item = _create(app_conn, world.owner, _saving(world))
    set_organization(owner_conn, world.owner.org, business_date=TODAY + timedelta(days=3))
    run(
        app_conn,
        "setup_recurring_revise",
        world.owner,
        item,
        *_saving(world, amount=1000, note="More").args(),
    )
    starts = owner_conn.execute(
        "SELECT start_on FROM setup.recurring_versions WHERE item_id = %s ORDER BY revision",
        (item,),
    ).fetchall()
    assert [r["start_on"] for r in starts] == [TODAY, TODAY]


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        (
            {"kind": 1, "frequency": 2, "day": 3, "condition": Jsonb({"min": "5000", "days": 1})},
            "recurring_condition_on_cost",
        ),
        ({"condition": Jsonb({"min": "0", "days": 1})}, "recurring_condition_min"),
        ({"condition": Jsonb({"min": "10.005", "days": 1})}, "recurring_condition_min"),
        ({"condition": Jsonb({"min": None, "days": 7})}, "recurring_condition_min"),
        ({"condition": Jsonb({"min": "5000", "days": 3})}, "recurring_condition_days"),
        (
            {
                "kind": 1,
                "frequency": 2,
                "day": 3,
                "opening": Jsonb({"date": "2026-03-01", "amounts": []}),
            },
            "recurring_opening_on_cost",
        ),
        ({"opening": Jsonb({"date": "2026-03-16", "amounts": []})}, "recurring_opening_future"),
        (
            {
                "opening": Jsonb(
                    {"date": "2026-03-01", "amounts": [{"vehicle_id": None, "amount": "-5"}]}
                )
            },
            "money_invalid",
        ),
        (
            {
                "opening": Jsonb(
                    {"date": "2026-03-01", "amounts": [{"vehicle_id": "x", "amount": "5"}]}
                )
            },
            "recurring_opening_vehicle",
        ),
        ({"end": date(2026, 12, 31)}, "recurring_savings_end"),
    ],
)
def test_the_rule_opening_and_end_checks_answer_with_their_codes(
    app_conn: Conn, world: World, changes: dict[str, Any], code: str
) -> None:
    definition = _saving(world, **changes)
    if definition.kind == 1:
        definition = replace(definition, expense_item_id=world.parking, start=TODAY)
    refuses(app_conn, "setup_recurring_create", world.owner, definition.args(), "XC422", code)


def test_an_opening_counts_from_its_date_and_a_run_on_that_date_is_not_counted_twice(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    item, _ = _daily(owner_conn, world, kind=2, since=5, on={world.kda: 500}, name="Owner savings")
    opening = Jsonb(
        {"date": str(_days(2)), "amounts": [{"vehicle_id": str(world.kda), "amount": "10000"}]}
    )
    definition = _saving(world, allocations=shares((world.kda, 500)), amount=500, opening=opening)
    assert (
        run(app_conn, "setup_recurring_revise", world.owner, item, *definition.args())["outcome"]
        == "updated"
    )
    listed = _list_item(app_conn, world.owner, item)
    assert Decimal(str(listed["balance"])) == Decimal("11000")
    assert listed["opening"] == {"date": str(_days(2)), "total": 10000}
    kept = replace(definition, note="A note")
    run(app_conn, "setup_recurring_revise", world.owner, item, *kept.args())
    assert _list_item(app_conn, world.owner, item)["opening"] == {
        "date": str(_days(2)),
        "total": 10000,
    }
    removed = replace(definition, note="A note", opening=Jsonb(None))
    run(app_conn, "setup_recurring_revise", world.owner, item, *removed.args())
    listed = _list_item(app_conn, world.owner, item)
    assert listed["opening"] is None
    assert Decimal(str(listed["balance"])) == Decimal("3000")


def test_a_saving_saved_with_a_rule_decides_its_runs_from_its_start(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    add_record(owner_conn, world.owner.org, world.kda, TODAY, 7000, recorder=world.owner.id)
    item = _create(
        app_conn, world.owner, _saving(world, condition=Jsonb({"min": "6000", "days": 1}))
    )
    assert _decided(owner_conn, item) == [(TODAY, 1, Decimal("7000.00"))]
    listed = _list_item(app_conn, world.owner, item)
    assert listed["condition"] == {"min": 6000, "days": 1}
    assert listed["last_run_states"] == {"saved": 1, "skipped": 0, "held": 0}


# --- the list and the summary --------------------------------------------------------------


def test_the_list_carries_the_pause_last_run_and_next_run(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    saving, _ = _daily(
        owner_conn,
        world,
        kind=2,
        since=3,
        on={world.kda: 300, world.kdb: 200},
        name="Owner savings",
    )
    cost, _ = _daily(owner_conn, world, since=3)
    listed = _list_item(app_conn, world.owner, saving)
    assert (listed["paused_from"], listed["last_run"], listed["last_run_vehicles"]) == (
        None,
        str(TODAY),
        2,
    )
    assert Decimal(str(listed["balance"])) == Decimal(2000)
    assert listed["next_run"] == str(TODAY + timedelta(days=1))
    assert (listed["condition"], listed["opening"]) == (None, None)
    run(app_conn, "setup_recurring_pause", world.owner, saving)
    listed = _list_item(app_conn, world.owner, saving)
    assert (listed["paused_from"], listed["next_run"]) == (str(TODAY), None)
    assert listed["last_run"] == str(_days(1))
    costs = _list_item(app_conn, world.owner, cost)
    assert (
        costs["last_run"],
        costs["last_run_vehicles"],
        costs["balance"],
        costs["last_run_states"],
    ) == (None, 0, None, None)


def test_the_summary_counts_the_month_and_hides_the_figures_of_a_kind_not_viewed(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    cost, _ = _daily(owner_conn, world, since=14)
    _daily(owner_conn, world, kind=2, since=1, name="Owner savings")
    paused, _ = _daily(owner_conn, world, name="Paused", on={world.kdb: 100})
    run(app_conn, "setup_recurring_pause", world.owner, paused)
    summary = read(app_conn, "setup_recurring_summary", world.owner)
    assert (summary["from_date"], summary["to_date"]) == ("2026-03-01", "2026-03-31")
    # The cost runs every day of March on KDA (500 x 31); the paused one ran 5 to 14 March.
    assert Decimal(str(summary["costs_due"])) == Decimal(500 * 31 + 100 * 10)
    assert Decimal(str(summary["saved"])) == Decimal(1000)
    assert Decimal(str(summary["savings_balance"])) == Decimal(1000)
    assert (summary["running_costs"], summary["paused_costs"]) == (1, 1)
    assert (summary["running_savings"], summary["paused_savings"]) == (1, 0)
    set_scope(owner_conn, world.clerk, world.owner.org, all_companies=True)
    set_override(owner_conn, world.clerk, "savings.view")
    hidden = read(app_conn, "setup_recurring_summary", world.clerk)
    assert (hidden["costs_due"], hidden["running_costs"], hidden["paused_costs"]) == (
        None,
        None,
        None,
    )
    assert Decimal(str(hidden["saved"])) == Decimal(1000)
    assert cost


def test_the_next_run_needs_a_share_vehicle_still_in_the_fleet(
    app_conn: Conn, owner_conn: Conn, world: World
) -> None:
    cost, _ = _daily(owner_conn, world, since=3, on={world.kda: 300, world.kdb: 200})
    retire = "UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s"
    owner_conn.execute(retire, (_days(2), world.kda))
    assert _list_item(app_conn, world.owner, cost)["next_run"] == str(TODAY + timedelta(days=1))
    owner_conn.execute(retire, (_days(1), world.kdb))
    assert _list_item(app_conn, world.owner, cost)["next_run"] is None


# --- the filters and the totals agree with the full postings -------------------------------


def _postings_seed(owner_conn: Conn, world: World) -> None:
    org, owner = world.owner.org, world.owner.id
    for day, vehicle, amount, removed in (
        (_days(4), world.kda, 900, False),
        (_days(2), world.kdb, 400, False),
        (_days(1), world.kda, 700, True),
    ):
        owner_conn.execute(
            "INSERT INTO expenses.entries (organization_id, id, entry_date, vehicle_id, "
            "expense_item_id, units, unit_amount, group_id, group_size, group_total, group_units, "
            "group_unit_amount, recorded_by, recorded_at, updated_by, updated_at, removed_by, "
            "removed_at, removal_reason) SELECT %(org)s, g.id, %(day)s, %(vehicle)s, %(item)s, 1, "
            "%(amount)s, g.id, 1, %(amount)s, 1, %(amount)s, %(owner)s, now(), %(owner)s, now(), "
            "CASE WHEN %(removed)s THEN %(owner)s::uuid END, CASE WHEN %(removed)s THEN now() END, "
            "CASE WHEN %(removed)s THEN 'Twice' END FROM (SELECT gen_random_uuid() AS id) AS g",
            {
                "org": org,
                "day": day,
                "vehicle": vehicle,
                "item": world.parking,
                "amount": amount,
                "owner": owner,
                "removed": removed,
            },
        )
    for day, vehicle, amount, status in (
        (_days(3), world.kdc, 250, 2),
        (_days(3), world.kda, 80, 1),
    ):
        owner_conn.execute(
            "INSERT INTO pettycash.entries (organization_id, holder_id, kind, entry_date, "
            "vehicle_id, expense_item_id, unit_amount, status, reviewed_by, reviewed_at, "
            "recorded_by, recorded_at, updated_by, updated_at) VALUES (%s, %s, 2, %s, %s, %s, %s, "
            "%s, CASE WHEN %s = 2 THEN %s::uuid END, CASE WHEN %s = 2 THEN now() END, %s, now(), "
            "%s, now())",
            (
                org,
                owner,
                day,
                vehicle,
                world.parking,
                amount,
                status,
                status,
                owner,
                status,
                owner,
                owner,
            ),
        )


def test_the_kind_and_item_filters_and_the_totals_agree_with_the_full_postings(
    app_conn: Conn, executor: Conn, owner_conn: Conn, world: World
) -> None:
    _daily(owner_conn, world, since=5, on={world.kda: 300, world.kdb: 200})
    saving, version = _daily(
        owner_conn, world, kind=2, since=5, on={world.kda: 100, world.kdc: 50}, name="Owner savings"
    )
    _rule(owner_conn, version, 6000, 1)
    spare, _ = _daily(owner_conn, world, kind=2, since=3, on={world.kdb: 70}, name="Spare savings")
    _capture(app_conn, world.owner, world.kda, _days(2), 7000)
    _capture(app_conn, world.owner, world.kda, _days(1), 4500)
    _postings_seed(owner_conn, world)
    vehicles = [world.kda, world.kdb, world.kdc]
    span = (vehicles, _days(6), TODAY, TODAY)
    runs = "SELECT item_id, run_on, vehicle_id, kind, amount, state FROM setup.scheduled_runs"
    with executor.transaction():
        executor.execute(
            "SELECT tenancy.enter_organization(%s, %s, 'req-filters', NULL)",
            (world.owner.id, world.owner.org),
        )
        every = executor.execute(f"{runs}(%s, %s, %s, %s)", span).fetchall()
        assert {r["state"] for r in every} == {0, 1, 2, 3}
        for kinds in ([1], [2], [1, 2]):
            kept = executor.execute(f"{runs}(%s, %s, %s, %s, %s)", (*span, kinds)).fetchall()
            assert sorted(map(str, kept)) == sorted(str(r) for r in every if r["kind"] in kinds)
        for items in ([saving], [spare], [saving, spare]):
            kept = executor.execute(f"{runs}(%s, %s, %s, %s, NULL, %s)", (*span, items)).fetchall()
            assert sorted(map(str, kept)) == sorted(str(r) for r in every if r["item_id"] in items)
        postings = executor.execute(
            "SELECT source, kind, day, vehicle_id, amount "
            "FROM setup.fleet_postings(%s, %s, %s, %s)",
            span,
        ).fetchall()
        assert {r["source"] for r in postings} == {1, 2, 3}
        costs = executor.execute(
            "SELECT source, kind, day, vehicle_id, amount "
            "FROM setup.fleet_postings(%s, %s, %s, %s, '{1}')",
            span,
        ).fetchall()
        assert sorted(map(str, costs)) == sorted(str(r) for r in postings if r["kind"] == 1)
        totals = executor.execute(
            "SELECT vehicle_id, money_out, saved, saving_runs "
            "FROM setup.fleet_totals(%s, %s, %s, %s)",
            span,
        ).fetchall()
        expected = {
            v: (
                sum(
                    (r["amount"] for r in postings if r["vehicle_id"] == v and r["kind"] == 1),
                    Decimal(0),
                ),
                sum(
                    (r["amount"] for r in postings if r["vehicle_id"] == v and r["kind"] == 2),
                    Decimal(0),
                ),
                sum(1 for r in postings if r["vehicle_id"] == v and r["kind"] == 2),
            )
            for v in vehicles
        }
        assert {
            r["vehicle_id"]: (r["money_out"], r["saved"], r["saving_runs"]) for r in totals
        } == expected
        assert expected[world.kda][0] > 0 and expected[world.kdb][1] > 0
        cost_only = executor.execute(
            "SELECT vehicle_id, money_out, saved FROM setup.fleet_totals(%s, %s, %s, %s, '{1}')",
            span,
        ).fetchall()
        assert {r["vehicle_id"]: (r["money_out"], r["saved"]) for r in cost_only} == {
            v: (money_out, Decimal(0)) for v, (money_out, _, _) in expected.items()
        }
