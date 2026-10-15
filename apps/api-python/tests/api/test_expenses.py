"""The central-expense routes against the real database (``docs/06-http-contract.md`` section
2.13.1): every route's answer in wire order, a purchase split into rows and its retry, each
refusal's sentence, the change and remove steps with the 409 and its ``current`` row, the
group detachment, who may change what, the ledger's three sources, figures, search, paging
and scope, the options, the change-log reasons, the route constraints, 401 and the statement
budget of 2 (however many rows the ledger holds).

The business date is 7 Oct 2026, a Wednesday (the test clock in Nairobi). Antony Maina owns
the organization, Peter Otieno is an Office admin (record and edit expenses) and Wanjiru
Kamau a Fleet manager who may record expenses on North Fleet only; the fleet, the catalogue,
petty-cash expenses and scheduled items are seeded as ``xcode_owner``."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from xcode_api.http.messages import MESSAGES
from xcode_api.http.routers.expenses import router

from ..support.client import ApiFactory, AuthApi
from ..support.rows import seed_organization
from ..support.setup_client import (
    FORBIDDEN,
    INVALID,
    NOT_FOUND,
    Member,
    empty,
    join,
    ok,
    problem,
    statements,
)
from ..support.setup_rows import Version, add_category, add_item, add_main_category, add_schedule
from ..support.tenancy import Member as Person
from ..support.tenancy import add_company, add_vehicle, set_override, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

TODAY = date(2026, 10, 7)
CHANGED = "This expense has changed."
LEDGER_KEYS = [
    "businessDate",
    "from",
    "to",
    "permissions",
    "figures",
    "items",
    "pageNumber",
    "pageSize",
    "total",
    "amount",
]
ROW_KEYS = [
    "id",
    "source",
    "date",
    "vehicleId",
    "registration",
    "expenseItemId",
    "itemName",
    "categoryName",
    "bucket",
    "units",
    "unitAmount",
    "total",
    "note",
    "recordedByName",
    "holderName",
    "scheduleId",
    "group",
    "version",
    "canEdit",
    "canRemove",
    "mainCategoryName",
    "fleetNumber",
]
GROUP_KEYS = ["id", "size", "total", "units", "unitAmount"]
VEHICLE_KEYS = ["id", "companyId", "companyName", "registration", "active", "fleetNumber"]
ITEM_KEYS = ["id", "name", "categoryId", "categoryName", "bucket", "mainCategoryName"]


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@dataclass(frozen=True)
class Depot:
    api: AuthApi
    org: UUID
    owner: Member
    admin: Member
    clerk: Member
    north: UUID
    kda: str
    kdb: str
    kdc: str
    tyres: str
    diesel: str


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


async def _person(api: AuthApi, org: UUID | None, role: str, phone: str, name: str) -> Member:
    joined = await join(api, email=f"{phone}@example.com", phone=phone, role=role)
    first, last = name.split()
    api.owner.execute(
        "UPDATE tenancy.memberships SET first_name = %s, last_name = %s WHERE user_id = %s",
        (first, last, joined.user_id),
    )
    if org is not None:
        set_scope(api.owner, joined.user_id, org, all_companies=True)
    return joined


@pytest.fixture
async def depot(api: AuthApi) -> Depot:
    owner = await _person(api, None, "Owner", "0711000211", "Antony Maina")
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    org = UUID(str(row["id"]))
    set_scope(api.owner, owner.user_id, org, all_companies=True)
    admin = await _person(api, org, "Office admin", "0722000211", "Peter Otieno")
    clerk = await _person(api, None, "Fleet manager", "0733000211", "Wanjiru Kamau")
    north = add_company(api.owner, org, "North Fleet")
    south = add_company(api.owner, org, "South Fleet")
    set_scope(api.owner, clerk.user_id, org, companies=[north])
    set_override(api.owner, Person(clerk.user_id, org, "", "", "", "", ""), "expenses.capture")
    joined = date(2026, 9, 1)
    kda = add_vehicle(api.owner, org, north, "KDA 103A", joined_on=joined, fleet_number="N-01")
    kdb = add_vehicle(api.owner, org, north, "KDB 204B", joined_on=joined)
    kdc = add_vehicle(api.owner, org, south, "KDC 305C", joined_on=joined)
    running = add_main_category(api.owner, org, "Running")
    repairs = add_category(api.owner, org, "Repairs", bucket=1, main_category=running)
    tyres = add_item(api.owner, org, repairs, "Tyres")
    diesel = add_item(
        api.owner, org, add_category(api.owner, org, "Fuelling", bucket=None), "Diesel"
    )
    return Depot(
        api, org, owner, admin, clerk, north, str(kda), str(kdb), str(kdc), str(tyres), str(diesel)
    )


def post(depot: Depot, who: Member, path: str, body: Any) -> Any:
    return depot.api.client.post(f"/setup/expenses{path}", json=body, headers=who.headers)


def put(depot: Depot, who: Member, path: str, body: Any) -> Any:
    return depot.api.client.put(f"/setup/expenses{path}", json=body, headers=who.headers)


def get(depot: Depot, who: Member, path: str) -> Any:
    return depot.api.client.get(f"/setup/expenses{path}", headers=who.headers)


def purchase(
    depot: Depot, units: Any, amount: Any, *shares: tuple[str, Any], **more: Any
) -> dict[str, Any]:
    body = {
        "date": TODAY.isoformat(),
        "expenseItemId": depot.tyres,
        "units": units,
        "unitAmount": amount,
        "allocations": [{"vehicleId": v, "amount": a} for v, a in shares],
    }
    return {**body, **more}


def line(depot: Depot, row: dict[str, Any], **more: Any) -> dict[str, Any]:
    """A change body that repeats the ledger row, with ``more`` on top."""
    body = {
        "date": row["date"],
        "vehicleId": row["vehicleId"],
        "expenseItemId": row["expenseItemId"],
        "units": row["units"],
        "unitAmount": row["unitAmount"],
        "note": row["note"],
        "version": row["version"],
    }
    return {**body, **more}


def ledger_path(start: str = day(-30), end: str = TODAY.isoformat(), **query: Any) -> str:
    extra = "".join(f"&{k}={v}" for k, v in query.items())
    return f"/ledger?from={start}&to={end}{extra}"


async def rows(depot: Depot, who: Member, **query: Any) -> list[dict[str, Any]]:
    return list(ok(await get(depot, who, ledger_path(**query)))["items"])


def reasons(depot: Depot) -> list[str]:
    return [
        str(r["reason"])
        for r in depot.api.owner.execute(
            "SELECT reason FROM tenancy.change_log WHERE section = 'centralexpenses' "
            "ORDER BY version"
        ).fetchall()
    ]


def sentence(code: str, **parameters: Any) -> str:
    text = MESSAGES[code].sentence(parameters)
    assert text is not None
    return text


def petty_expense(depot: Depot, vehicle: str, on: str, amount: Any, status: int = 2) -> str:
    row = depot.api.owner.execute(
        "INSERT INTO pettycash.entries (organization_id, holder_id, kind, entry_date, vehicle_id, "
        "expense_item_id, unit_amount, status, reviewed_by, reviewed_at, recorded_by, "
        "recorded_at, updated_by, updated_at) VALUES (%s, %s, 2, %s, %s, %s, %s, %s, %s, "
        "CASE WHEN %s = 2 THEN now() END, %s, now(), %s, now()) RETURNING id",
        (
            depot.org,
            depot.clerk.user_id,
            on,
            vehicle,
            depot.diesel,
            Decimal(str(amount)),
            status,
            depot.owner.user_id if status == 2 else None,
            status,
            depot.clerk.user_id,
            depot.clerk.user_id,
        ),
    ).fetchone()
    assert row is not None
    return str(row["id"])


# --- record a purchase ------------------------------------------------------------------------


async def test_one_vehicle_records_one_row_and_its_log(depot: Depot) -> None:
    chosen = str(uuid4())
    body = purchase(depot, 2, 2000, (depot.kda, 4000), id=chosen, note=" Two tyres ")
    response, count = await statements(post(depot, depot.admin, "/entries", body))
    made = ok(response)
    assert count == 2
    assert list(made) == ["ids", "total"]
    assert response.content == f'{{"ids":["{chosen}"],"total":4000}}'.encode()
    [row] = await rows(depot, depot.admin)
    assert list(row) == ROW_KEYS
    assert row == {
        "id": chosen,
        "source": "central",
        "date": TODAY.isoformat(),
        "vehicleId": depot.kda,
        "registration": "KDA 103A",
        "expenseItemId": depot.tyres,
        "itemName": "Tyres",
        "categoryName": "Repairs",
        "bucket": 1,
        "units": 2,
        "unitAmount": 2000,
        "total": 4000,
        "note": "Two tyres",
        "recordedByName": "Peter Otieno",
        "holderName": None,
        "scheduleId": None,
        "group": None,
        "version": 1,
        "canEdit": True,
        "canRemove": True,
        "mainCategoryName": "Running",
        "fleetNumber": "N-01",
    }
    assert reasons(depot) == [
        "Recorded central expense on KDA 103A for 7 Oct 2026: Tyres, KES 4,000"
    ]


async def test_even_and_uneven_splits_keep_the_purchase_on_every_row(depot: Depot) -> None:
    even = ok(
        await post(
            depot, depot.admin, "/entries", purchase(depot, 10, 4, (depot.kda, 20), (depot.kdb, 20))
        )
    )
    assert (len(even["ids"]), even["total"]) == (2, 40)
    uneven = ok(
        await post(
            depot,
            depot.admin,
            "/entries",
            purchase(
                depot, 1, 100, (depot.kda, "33.34"), (depot.kdb, "33.33"), (depot.kdc, "33.33")
            ),
        )
    )
    assert uneven["total"] == 100
    listed = {r["id"]: r for r in await rows(depot, depot.admin)}
    assert [(listed[i]["units"], listed[i]["unitAmount"]) for i in even["ids"]] == [(5, 4), (5, 4)]
    assert [listed[i]["total"] for i in uneven["ids"]] == [33.34, 33.33, 33.33]
    group = listed[uneven["ids"][0]]["group"]
    assert list(group) == GROUP_KEYS
    assert {k: group[k] for k in ("size", "total", "units", "unitAmount")} == {
        "size": 3,
        "total": 100,
        "units": 1,
        "unitAmount": 100,
    }
    assert {listed[i]["group"]["id"] for i in uneven["ids"]} == {group["id"]}


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"allocations": []}, "expense_vehicles_invalid"),
        ({"allocations": None}, "expense_vehicles_invalid"),
        ({"units": 0}, "pettycash_line_units"),
        ({"unitAmount": "100.005"}, "pettycash_line_amount_decimals"),
        ({"note": "n" * 81}, "pettycash_line_note_length"),
        ({"expenseItemId": None}, "pettycash_line_item_required"),
        ({"date": None}, "pettycash_line_date_required"),
    ],
)
async def test_a_bad_purchase_is_refused_with_its_sentence(
    depot: Depot, body: dict[str, Any], code: str
) -> None:
    sent = purchase(depot, 1, 100, (depot.kda, 50), (depot.kdb, 50))
    problem(
        await post(depot, depot.admin, "/entries", {**sent, **body}), 400, INVALID, sentence(code)
    )


@pytest.mark.parametrize(
    ("shares", "code"),
    [
        ((("a", "50.005"), ("b", "49.995")), "expense_allocation_amount"),
        ((("a", 0), ("b", 100)), "expense_allocation_amount"),
        ((("a", 150), ("b", -50)), "expense_allocation_sign"),
        ((("a", 60), ("b", 50)), "expense_allocation_sum"),
        ((("a", 50), ("a", 50)), "expense_vehicles_invalid"),
    ],
)
async def test_each_vehicles_amount_is_checked_exactly(
    depot: Depot, shares: tuple[tuple[str, Any], ...], code: str
) -> None:
    vehicle = {"a": depot.kda, "b": depot.kdb}
    body = purchase(depot, 1, 100, *((vehicle[v], a) for v, a in shares))
    problem(await post(depot, depot.admin, "/entries", body), 400, INVALID, sentence(code))


async def test_vehicles_dates_and_items_are_checked_and_the_options_follow_the_date(
    depot: Depot,
) -> None:
    api = depot.api
    tomorrow = purchase(depot, 1, 100, (depot.kda, 100), date=day(1))
    problem(
        await post(depot, depot.admin, "/entries", tomorrow),
        400,
        INVALID,
        sentence("expense_date_future"),
    )
    old = purchase(depot, 1, 100, (depot.kda, 100), date=day(-3651))
    problem(
        await post(depot, depot.admin, "/entries", old),
        400,
        INVALID,
        sentence("expense_date_too_old"),
    )
    hidden = purchase(depot, 1, 100, (depot.kdc, 100))
    problem(
        await post(depot, depot.clerk, "/entries", hidden),
        400,
        INVALID,
        sentence("expense_vehicle_not_yours"),
    )
    api.owner.execute(
        "INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, "
        "returned_on) "
        "VALUES (%s, %s, %s, %s)",
        (depot.org, depot.kdb, day(-2), day(3)),
    )
    away = purchase(depot, 1, 100, (depot.kda, 50), (depot.kdb, 50))
    problem(
        await post(depot, depot.admin, "/entries", away),
        400,
        INVALID,
        "KDB 204B was not in the fleet on that day.",
    )
    stopped = purchase(depot, 1, 100, (depot.kda, 100), expenseItemId=str(uuid4()))
    problem(
        await post(depot, depot.admin, "/entries", stopped),
        400,
        INVALID,
        sentence("expense_item_not_in_use"),
    )
    options = ok(await get(depot, depot.clerk, "/options"))
    assert list(options) == ["vehicles", "items"]
    assert [list(v) for v in options["vehicles"]] == [VEHICLE_KEYS]
    assert [v["registration"] for v in options["vehicles"]] == ["KDA 103A"]
    assert [list(i) for i in options["items"]] == [ITEM_KEYS, ITEM_KEYS]
    assert [(i["name"], i["bucket"], i["mainCategoryName"]) for i in options["items"]] == [
        ("Diesel", 2, None),
        ("Tyres", 1, "Running"),
    ]
    earlier = ok(await get(depot, depot.admin, f"/options?date={day(-3)}"))
    assert [v["registration"] for v in earlier["vehicles"]] == ["KDA 103A", "KDB 204B", "KDC 305C"]
    problem(
        await get(depot, depot.admin, f"/options?date={day(1)}"),
        400,
        INVALID,
        sentence("expense_date_future"),
    )


async def test_a_retried_purchase_answers_its_rows_and_a_stolen_id_is_a_conflict(
    depot: Depot,
) -> None:
    single, split = str(uuid4()), str(uuid4())
    alone = purchase(depot, 1, 1200, (depot.kda, 1200), id=single)
    first = ok(await post(depot, depot.owner, "/entries", alone))
    again = ok(await post(depot, depot.owner, "/entries", alone))
    assert again == first == {"ids": [single], "total": 1200}
    body = purchase(depot, 3, 100, (depot.kda, 100), (depot.kdb, 100), (depot.kdc, 100), id=split)
    made = ok(await post(depot, depot.owner, "/entries", body))
    retried = ok(await post(depot, depot.owner, "/entries", body))
    assert retried == {"ids": sorted(made["ids"]), "total": 300}
    other = purchase(depot, 1, 50, (depot.kdb, 50), id=split)
    assert ok(await post(depot, depot.owner, "/entries", other)) == retried
    today = ledger_path(TODAY.isoformat())
    assert ok(await get(depot, depot.owner, today))["total"] == 4
    assert len(reasons(depot)) == 4
    for taken in (single, split):
        stolen = problem(
            await post(depot, depot.admin, "/entries", {**other, "id": taken}),
            409,
            CHANGED,
            sentence("expense_saved_by_other"),
        )
        assert "current" not in stolen
    assert ok(await get(depot, depot.owner, today))["total"] == 4
    problem(
        await post(depot, depot.owner, "/entries", {**other, "id": made["ids"][0]}),
        409,
        CHANGED,
        sentence("expense_saved_by_other"),
    )


async def test_unknown_properties_never_reach_the_stored_purchase(depot: Depot) -> None:
    """Stored columns are the routine's: a body naming them is read for its fields only."""
    stored = {
        "total": 1,
        "groupTotal": 1,
        "groupSize": 9,
        "version": 9,
        "recordedBy": str(depot.owner.user_id),
        "recordedByName": "Antony Maina",
        "organizationId": str(uuid4()),
    }
    body = purchase(depot, 1, 100, (depot.kda, 100))
    made = ok(await post(depot, depot.clerk, "/entries", {**body, **stored}))
    assert made["total"] == 100
    row = (await rows(depot, depot.owner))[0]
    assert (row["total"], row["version"], row["recordedByName"], row["group"]) == (
        100,
        1,
        "Wanjiru Kamau",
        None,
    )
    change = {**line(depot, row, unitAmount=120), **stored, "version": 1}
    saved = ok(await put(depot, depot.clerk, f"/entries/{row['id']}", change))
    assert saved == {"id": row["id"], "version": 2}
    after = (await rows(depot, depot.owner))[0]
    assert (after["total"], after["recordedByName"]) == (120, "Wanjiru Kamau")


# --- change and remove ----------------------------------------------------------------------


async def test_a_change_replays_an_identical_line_and_a_stale_one_is_a_409_with_the_row(
    depot: Depot,
) -> None:
    made = ok(await post(depot, depot.admin, "/entries", purchase(depot, 1, 300, (depot.kda, 300))))
    [row] = await rows(depot, depot.admin)
    path = f"/entries/{made['ids'][0]}"
    response, count = await statements(put(depot, depot.admin, path, line(depot, row)))
    assert (ok(response), count) == ({"id": row["id"], "version": 1}, 2)
    moved = ok(
        await put(depot, depot.admin, path, line(depot, row, date=day(-1), vehicleId=depot.kdb))
    )
    assert moved == {"id": row["id"], "version": 2}
    stale = problem(
        await put(depot, depot.admin, path, line(depot, row, unitAmount=350)),
        409,
        CHANGED,
        sentence("expense_version_conflict"),
    )
    [now] = await rows(depot, depot.admin)
    assert stale["current"] == now
    assert (now["date"], now["registration"], now["version"]) == (day(-1), "KDB 204B", 2)
    problem(
        await put(depot, depot.admin, path, line(depot, now, unitAmount=350, version=None)),
        400,
        INVALID,
        sentence("expense_version_required"),
    )
    assert reasons(depot)[-1] == (
        "Changed central expense on KDB 204B for 6 Oct 2026: Tyres, KES 300"
    )


async def test_a_new_item_units_or_amount_takes_a_row_out_of_its_group_and_keeps_the_key(
    depot: Depot,
) -> None:
    chosen = str(uuid4())
    body = purchase(depot, 2, 100, (depot.kda, 100), (depot.kdb, 100), id=chosen)
    made = ok(await post(depot, depot.admin, "/entries", body))
    listed = {r["id"]: r for r in await rows(depot, depot.admin)}
    first, second = (listed[i] for i in made["ids"])
    ok(await put(depot, depot.admin, f"/entries/{first['id']}", line(depot, first, note="Fitted")))
    ok(await put(depot, depot.admin, f"/entries/{second['id']}", line(depot, second, units=2)))
    after = {r["id"]: r for r in await rows(depot, depot.admin)}
    assert after[first["id"]]["group"]["size"] == 2
    assert after[second["id"]]["group"] is None
    problem(
        await put(
            depot,
            depot.admin,
            f"/entries/{first['id']}",
            line(depot, after[first["id"]], vehicleId=depot.kdb),
        ),
        400,
        INVALID,
        "This purchase already has a row for KDB 204B.",
    )
    again = ok(await post(depot, depot.admin, "/entries", body))
    assert again["ids"] == sorted(made["ids"])


async def test_removing_needs_a_reason_and_takes_the_row_out_of_the_ledger_and_the_report(
    depot: Depot,
) -> None:
    made = ok(
        await post(depot, depot.admin, "/entries", purchase(depot, 1, 4000, (depot.kda, 4000)))
    )
    path = f"/entries/{made['ids'][0]}/remove"
    problem(
        await post(depot, depot.admin, path, {"version": 1}),
        400,
        INVALID,
        sentence("reason_length"),
    )
    response, count = await statements(
        post(depot, depot.admin, path, {"version": 1, "reason": " Recorded twice "})
    )
    assert (ok(response), count) == ({"id": made["ids"][0], "version": 2}, 2)
    assert await rows(depot, depot.admin) == []
    assert reasons(depot)[-1] == (
        "Removed central expense on KDA 103A for 7 Oct 2026: Tyres, KES 4,000."
        " Reason: Recorded twice."
    )
    report = ok(
        await depot.api.client.get(
            f"/setup/vehicles/{depot.kda}/report?from={day(-1)}&through={TODAY.isoformat()}",
            headers=depot.owner.headers,
        )
    )
    assert [p for p in report["postings"] if p.get("source") == "central"] == []
    empty_or_problem = await post(depot, depot.admin, path, {"version": 2, "reason": "Again"})
    problem(empty_or_problem, 404, NOT_FOUND)


async def test_recording_alone_changes_only_its_own_rows_of_the_day(depot: Depot) -> None:
    mine = ok(await post(depot, depot.clerk, "/entries", purchase(depot, 1, 100, (depot.kda, 100))))
    theirs = ok(
        await post(depot, depot.admin, "/entries", purchase(depot, 1, 100, (depot.kda, 100)))
    )
    listed = {r["id"]: r for r in await rows(depot, depot.clerk)}
    assert (listed[mine["ids"][0]]["canEdit"], listed[theirs["ids"][0]]["canEdit"]) == (True, False)
    other = listed[theirs["ids"][0]]
    problem(
        await put(
            depot, depot.clerk, f"/entries/{other['id']}", line(depot, other, unitAmount=120)
        ),
        403,
        FORBIDDEN,
        'Changing someone else\'s expense needs the permission "Edit an expense".',
    )
    own = listed[mine["ids"][0]]
    problem(
        await put(depot, depot.clerk, f"/entries/{own['id']}", line(depot, own, date=day(-1))),
        403,
        FORBIDDEN,
        'Changing the date of an expense needs the permission "Edit an expense".',
    )
    ok(await put(depot, depot.clerk, f"/entries/{own['id']}", line(depot, own, unitAmount=120)))
    ok(
        await post(
            depot, depot.admin, f"/entries/{other['id']}/remove", {"version": 1, "reason": "x"}
        )
    )


# --- the ledger -------------------------------------------------------------------------------


async def test_the_ledger_lists_three_sources_newest_first_and_never_savings(depot: Depot) -> None:
    api = depot.api
    ok(await post(depot, depot.admin, "/entries", purchase(depot, 1, 4000, (depot.kda, 4000))))
    petty = petty_expense(depot, depot.kda, day(-1), 300)
    petty_expense(depot, depot.kda, day(-1), 999, status=1)
    item, _ = add_schedule(
        api.owner,
        depot.org,
        Version(
            date(2026, 9, 1), {UUID(depot.kda): Decimal(700)}, name="Insurance", day=5, bucket=3
        ),
    )
    add_schedule(
        api.owner,
        depot.org,
        Version(date(2026, 9, 1), {UUID(depot.kda): Decimal(900)}, name="Rainy day", kind=2, day=5),
    )
    response, count = await statements(get(depot, depot.owner, ledger_path()))
    seen = ok(response)
    assert count == 2
    assert list(seen) == LEDGER_KEYS
    assert seen["figures"] == {"total": 5000, "central": 4000, "pettyCash": 300, "scheduled": 700}
    assert seen["permissions"] == {"canRecord": True, "canCorrect": True}
    assert (seen["businessDate"], seen["from"], seen["to"]) == (
        TODAY.isoformat(),
        day(-30),
        TODAY.isoformat(),
    )
    assert [(r["source"], r["date"]) for r in seen["items"]] == [
        ("central", TODAY.isoformat()),
        ("pettycash", day(-1)),
        ("scheduled", day(-2)),
    ]
    assert seen["items"][1]["id"] == petty
    assert (seen["items"][1]["holderName"], seen["items"][1]["canEdit"]) == ("Wanjiru Kamau", False)
    scheduled = seen["items"][2]
    assert (
        scheduled["id"],
        scheduled["scheduleId"],
        scheduled["itemName"],
        scheduled["recordedByName"],
    ) == (
        f"{item}:{day(-2)}:{depot.kda}",
        str(item),
        "Insurance",
        None,
    )


async def test_source_and_search_narrow_the_rows_not_the_figures_and_pages_are_cut(
    depot: Depot,
) -> None:
    for vehicle, amount, note in (
        (depot.kda, 100, "Front tyres"),
        (depot.kdb, 200, "Rear tyres"),
        (depot.kdb, 300, "50% off_sale"),
    ):
        body = purchase(depot, 1, amount, (vehicle, amount), note=note)
        ok(await post(depot, depot.admin, "/entries", body))
    petty_expense(depot, depot.kda, TODAY.isoformat(), 50)
    whole = ok(await get(depot, depot.admin, ledger_path()))
    assert (whole["total"], whole["amount"]) == (4, 650)
    narrowed = ok(await get(depot, depot.admin, ledger_path(source="central", q="KDB")))
    assert narrowed["figures"] == whole["figures"]
    assert (narrowed["total"], narrowed["amount"]) == (2, 500)
    literal = ok(await get(depot, depot.admin, ledger_path(q="%25 off_")))
    assert [r["note"] for r in literal["items"]] == ["50% off_sale"]
    pages = [ok(await get(depot, depot.admin, ledger_path(page=n, pageSize=3))) for n in (1, 2)]
    assert [len(p["items"]) for p in pages] == [3, 1]
    assert [r["id"] for p in pages for r in p["items"]] == [r["id"] for r in whole["items"]]
    for query, code in (
        ("&source=fuel", "expense_source_invalid"),
        ("&q=" + "q" * 201, "expense_search_length"),
        ("&page=0", "page_out_of_range"),
    ):
        problem(await get(depot, depot.admin, ledger_path() + query), 400, INVALID, sentence(code))
    problem(
        await get(depot, depot.admin, f"/ledger?from={TODAY.isoformat()}"),
        400,
        INVALID,
        sentence("expense_period_required"),
    )
    problem(
        await get(depot, depot.admin, ledger_path(day(-367))),
        400,
        INVALID,
        sentence("expense_period_length"),
    )


async def test_a_scoped_person_sees_nothing_outside_their_vehicles_change_log_included(
    depot: Depot,
) -> None:
    api = depot.api
    set_override(
        api.owner, Person(depot.clerk.user_id, depot.org, "", "", "", "", ""), "audit.view"
    )
    split = purchase(depot, 2, 1000, (depot.kda, 1000), (depot.kdc, 1000))
    ok(await post(depot, depot.owner, "/entries", split))
    alone = purchase(depot, 1, 4000, (depot.kdc, 4000))
    hidden = ok(await post(depot, depot.owner, "/entries", alone))["ids"][0]
    add_schedule(
        api.owner,
        depot.org,
        Version(
            TODAY - timedelta(days=10),
            {UUID(depot.kdc): Decimal(300)},
            name="Parking",
            frequency=2,
            day=TODAY.isoweekday() % 7,
        ),
    )
    petty_expense(depot, depot.kdc, TODAY.isoformat(), 900)
    today = ledger_path(TODAY.isoformat())
    everything = ok(await get(depot, depot.owner, today))
    assert (everything["figures"]["total"], everything["total"]) == (7200, 5)
    mine = ok(await get(depot, depot.clerk, today))
    assert [r["vehicleId"] for r in mine["items"]] == [depot.kda]
    assert (mine["figures"], mine["total"], mine["amount"]) == (
        {"total": 1000, "central": 1000, "pettyCash": 0, "scheduled": 0},
        1,
        1000,
    )
    assert ok(await get(depot, depot.clerk, ledger_path(TODAY.isoformat(), q="KDC")))["total"] == 0
    options = ok(await get(depot, depot.clerk, f"/options?date={TODAY.isoformat()}"))
    assert depot.kdc not in [v["id"] for v in options["vehicles"]]
    change = {
        "date": TODAY.isoformat(),
        "vehicleId": depot.kdc,
        "expenseItemId": depot.tyres,
        "units": 1,
        "unitAmount": 1,
        "version": 1,
    }
    problem(await put(depot, depot.clerk, f"/entries/{hidden}", change), 404, NOT_FOUND)
    removal = {"version": 1, "reason": "Not mine"}
    problem(await post(depot, depot.clerk, f"/entries/{hidden}/remove", removal), 404, NOT_FOUND)
    problem(
        await post(depot, depot.clerk, "/entries", purchase(depot, 1, 10, (depot.kdc, 10))),
        400,
        INVALID,
        sentence("expense_vehicle_not_yours"),
    )
    log = "/setup/history?section=centralexpenses&pageSize=100"
    seen = ok(await api.client.get(log, headers=depot.clerk.headers))["items"]
    assert len(ok(await api.client.get(log, headers=depot.owner.headers))["items"]) == 3
    assert [i["reason"] for i in seen] == [
        "Recorded central expense on KDA 103A for 7 Oct 2026: Tyres, KES 1,000"
    ]


async def test_another_organizations_rows_and_ids_stay_its_own(depot: Depot) -> None:
    """Another organization's purchase under the same id is neither a retry nor a conflict
    here, its row stays as it was and never reaches this ledger."""
    other = seed_organization(depot.api.owner)
    theirs = "SELECT * FROM expenses.entries WHERE organization_id = %s AND id = %s"
    before = depot.api.owner.execute(theirs, (other.org, other.central)).fetchone()
    body = purchase(depot, 1, 100, (depot.kda, 100), id=str(other.central))
    made = ok(await post(depot, depot.admin, "/entries", body))
    assert made == {"ids": [str(other.central)], "total": 100}
    assert depot.api.owner.execute(theirs, (other.org, other.central)).fetchone() == before
    seen = ok(await get(depot, depot.owner, ledger_path("2026-01-01", TODAY.isoformat())))
    assert [r["vehicleId"] for r in seen["items"]] == [depot.kda]


async def test_the_ledger_reads_with_two_statements_however_many_rows(depot: Depot) -> None:
    api = depot.api
    for n in (5, 150, 300):
        api.owner.execute(
            "INSERT INTO expenses.entries (organization_id, id, entry_date, vehicle_id, "
            "expense_item_id, units, unit_amount, group_id, group_size, group_total, group_units, "
            "group_unit_amount, recorded_by, recorded_at, updated_by, updated_at) "
            "SELECT %s, n.id, %s::date - (n.s %% 30), %s, %s, 1, 10, n.id, 1, 10, 1, 10, %s, "
            "now(), %s, now() FROM (SELECT gen_random_uuid() AS id, s "
            "FROM generate_series(1, %s) AS s) AS n",
            (depot.org, TODAY, depot.kda, depot.tyres, depot.admin.user_id, depot.admin.user_id, n),
        )
        response, count = await statements(get(depot, depot.admin, ledger_path(pageSize=100)))
        assert count == 2
        assert ok(response)["pageSize"] == 100


async def test_every_route_keeps_the_statement_budget_of_two(depot: Depot) -> None:
    budget: dict[str, int] = {}

    async def spend(name: str, call: Awaitable[Any]) -> Any:
        response, budget[name] = await statements(call)
        return ok(response)

    made = await spend(
        "record", post(depot, depot.admin, "/entries", purchase(depot, 1, 50, (depot.kda, 50)))
    )
    [row] = (await spend("ledger", get(depot, depot.admin, ledger_path())))["items"]
    await spend("options", get(depot, depot.admin, "/options"))
    await spend(
        "change",
        put(depot, depot.admin, f"/entries/{made['ids'][0]}", line(depot, row, unitAmount=60)),
    )
    await spend(
        "remove",
        post(
            depot, depot.admin, f"/entries/{made['ids'][0]}/remove", {"version": 2, "reason": "x"}
        ),
    )
    assert budget == dict.fromkeys(["record", "ledger", "options", "change", "remove"], 2)


async def test_the_routes_refuse_a_bad_id_no_bearer_and_a_person_without_the_rights(
    depot: Depot,
) -> None:
    empty(await post(depot, depot.admin, "/entries/not-a-uuid/remove", {"version": 1}), 404)
    response = await depot.api.client.get("/setup/expenses/options")
    assert response.status_code == 401
    nobody = await _person(depot.api, depot.org, "Revenue clerk", "0744000211", "Rita Clerk")
    problem(await get(depot, nobody, ledger_path()), 403, FORBIDDEN)
    problem(await get(depot, nobody, "/options"), 403, FORBIDDEN)
    problem(
        await post(depot, nobody, "/entries", purchase(depot, 1, 5, (depot.kda, 5))), 403, FORBIDDEN
    )
    response = await post(depot, depot.admin, f"/entries/{uuid4()}/remove", {"version": 2**63})
    body = problem(response, 400, INVALID, response.json().get("detail"))
    assert list(body["errors"]) == ["version"]


OPERATIONS = {
    ("GET", "/setup/expenses/ledger"): "GetExpenseLedger",
    ("GET", "/setup/expenses/options"): "GetExpenseOptions",
    ("POST", "/setup/expenses/entries"): "RecordExpense",
    ("PUT", "/setup/expenses/entries/{id:uuid}"): "ChangeExpense",
    ("POST", "/setup/expenses/entries/{id:uuid}/remove"): "RemoveExpense",
}


async def test_every_central_expense_route_has_its_operation_id_and_tag() -> None:
    routes = {
        (method, getattr(route, "path", "")): getattr(route, "operation_id", None)
        for route in router.routes
        for method in getattr(route, "methods", ())
    }
    assert {key: routes.get(key) for key in OPERATIONS} == OPERATIONS
    assert {tuple(getattr(route, "tags", ())) for route in router.routes} == {("Central expenses",)}


# --- the export (E02; stream R's route over this world) ---


async def test_an_exported_item_starting_with_equals_stays_text(depot: Depot) -> None:
    """A text that Excel would read as a formula is written as a text cell with the quote
    prefix, so a catalogue name like ``=2+2`` cannot run as one in the exported ledger."""
    from urllib.parse import quote

    from ..support.export_files import Workbook

    odd = add_category(depot.api.owner, depot.org, "Odd", bucket=1)
    item = add_item(depot.api.owner, depot.org, odd, "=2+2")
    body = purchase(depot, 1, 500, (depot.kda, 500), expenseItemId=str(item))
    ok(await post(depot, depot.admin, "/entries", body))
    path = f"/export?from={day(-30)}&to={TODAY.isoformat()}&q={quote('=2+2', safe='')}"
    response = await get(depot, depot.admin, path)
    assert response.status_code == 200, response.content
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="Central expenses '
    )
    book = Workbook(response.content)
    assert not book.has_formulas
    assert book.text("C9") == "=2+2"
    assert book.xf("C9").get("quotePrefix") == "1"
    assert book.text("A10") == "1 row"
