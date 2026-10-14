"""The scheduled expense and saving routes against the real database
(``docs/06-http-contract.md`` section 2.4): the list in wire order with allocations, partial
items for a scoped viewer and the active amount, the vehicle options, create of a cost (named
after its expense item) and of a saving, revise with the change sentence and the unchanged
revise, the refusals of the save with their exact sentences, stop (a JSON body with the
confirmation and a reason) and restore (cancel the stop, no body read), the change-log entries
each write leaves with their JSON text snapshots, the 415, 401, 403 and 404 answers, the paging
refusals and the statement budget of 2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pytest

from ..support.client import ApiFactory, AuthApi
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
from ..support.tenancy import Member as Person
from ..support.tenancy import set_override, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

RECURRING_KEYS = [
    "id",
    "versionId",
    "revision",
    "name",
    "kind",
    "amount",
    "frequency",
    "day",
    "lastDay",
    "start",
    "end",
    "stoppedFrom",
    "allocations",
    "partial",
    "expenseItemId",
    "expenseItemName",
    "bucket",
    "note",
    "month",
    "activeAmount",
    "pausedFrom",
    "lastRun",
    "lastRunVehicles",
    "balance",
    "lastRunStates",
    "condition",
    "opening",
    "nextRun",
]
ALLOCATION_KEYS = ["vehicleId", "amount", "registration", "active"]
OPTION_KEYS = ["id", "companyId", "companyName", "registration", "active", "fleetNumber"]
ENTRY_KEYS = [
    "version",
    "section",
    "entityId",
    "reason",
    "occurredAt",
    "actorId",
    "actorName",
    "before",
    "after",
]
PAGING = "Page must be 1\u2013100000 and page size 1\u2013100."
REASON_LENGTH = "A reason of 1\u2013500 characters is required."
MONEY = "Amount must be positive with at most two decimal places."
SHAPE = (
    "Choose a weekday (0\u20136), a month day (1\u201328 / last), or for yearly a month "
    "(1\u201312) and a day."
)
STOP_CONFIRM = (
    "Confirm stopping this item. Past postings are retained; no posting occurs from today."
)
KIND_FILTER = "Kind must be cost or savings."
STATUS_FILTER = "Status must be running or stopped."
UNSTORABLE = "Text cannot contain U+0000 or an unpaired surrogate."
UNKNOWN = "00000000-0000-4000-8000-000000000000"


@dataclass(frozen=True, slots=True)
class Fleet:
    north: str
    south: str
    kda: str
    kdb: str
    kdc: str
    parking: str
    spares: str
    repayment: str


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


async def post_id(api: AuthApi, member: Member, path: str, body: dict[str, Any]) -> str:
    response = await api.client.post(path, json=body, headers=member.headers)
    return str(ok(response)["id"])


@pytest.fixture
async def fleet(api: AuthApi, owner: Member) -> Fleet:
    north = await post_id(api, owner, "/setup/companies", {"name": "North Star"})
    south = await post_id(api, owner, "/setup/companies", {"name": "South Line"})

    async def vehicle(company: str, registration: str) -> str:
        body = {
            "companyId": company,
            "registration": registration,
            "fleetNumber": registration.replace(" ", "")[-4:],
            "joinedOn": "2026-10-01",
            "dayTargets": [1000] * 7,
        }
        return await post_id(api, owner, "/setup/vehicles", body)

    async def category(name: str, bucket: int) -> str:
        """A category with the bucket a pre-0010 category kept (S33 no longer writes one)."""
        created = await post_id(api, owner, "/setup/expense-categories", {"name": name})
        api.owner.execute(
            "UPDATE setup.expense_categories SET bucket = %s WHERE id = %s",
            (bucket, UUID(created)),
        )
        return created

    async def item(category_id: str, name: str) -> str:
        return await post_id(
            api, owner, f"/setup/expense-categories/{category_id}/items", {"name": name}
        )

    charges = await category("Charges", 2)
    garage = await category("Garage and repairs", 1)
    loans = await category("Loans", 3)
    return Fleet(
        north=north,
        south=south,
        kda=await vehicle(north, "KDA 482M"),
        kdb=await vehicle(north, "KDB 111A"),
        kdc=await vehicle(south, "KDC 200B"),
        parking=await item(charges, "Parking"),
        spares=await item(garage, "Spares"),
        repayment=await item(loans, "Loan repayment"),
    )


def organization(api: AuthApi) -> UUID:
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    return UUID(str(row["id"]))


def saving(fleet: Fleet, **changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Owner savings",
        "kind": 2,
        "amount": 1000,
        "frequency": 2,
        "day": 5,
        "start": "2026-10-07",
        "allocations": [{"vehicleId": fleet.kda, "amount": 1000}],
    }
    body.update(changes)
    return body


def cost(fleet: Fleet, **changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Typed name",
        "kind": 1,
        "amount": 1200,
        "frequency": 2,
        "day": 5,
        "start": "2026-10-01",
        "allocations": [{"vehicleId": fleet.kda, "amount": 1200}],
        "expenseItemId": fleet.parking,
    }
    body.update(changes)
    return body


async def create(api: AuthApi, member: Member, body: dict[str, Any]) -> str:
    response = await api.client.post("/setup/recurring", json=body, headers=member.headers)
    created = ok(response)
    assert list(created) == ["id"]
    return str(created["id"])


async def revise(api: AuthApi, member: Member, item: str, body: dict[str, Any]) -> Any:
    response = await api.client.put(f"/setup/recurring/{item}", json=body, headers=member.headers)
    return ok(response)


async def rows(api: AuthApi, member: Member) -> list[dict[str, Any]]:
    page = ok(await api.client.get("/setup/recurring?pageSize=100", headers=member.headers))
    items: list[dict[str, Any]] = page["items"]
    return items


async def row(api: AuthApi, member: Member, item: str) -> dict[str, Any]:
    (found,) = [r for r in await rows(api, member) if r["id"] == item]
    return found


async def entries(api: AuthApi, member: Member) -> list[dict[str, Any]]:
    """The scheduled item change log, newest first."""
    page = ok(
        await api.client.get(
            "/setup/history?section=recurring&pageSize=100", headers=member.headers
        )
    )
    items: list[dict[str, Any]] = page["items"]
    return items


async def reasons(api: AuthApi, member: Member) -> list[str]:
    return [entry["reason"] for entry in reversed(await entries(api, member))]


def stopped_from(api: AuthApi, item: str, day: date | None) -> None:
    api.owner.execute(
        "UPDATE setup.recurring_items SET stopped_from = %s WHERE id = %s", (day, UUID(item))
    )


async def scoped(api: AuthApi, fleet: Fleet, *grants: str) -> Member:
    """A person with the given grants who reaches North Star only."""
    member = await join(api, email="sam@example.com", phone="0733000111", role="Fleet manager")
    org = organization(api)
    for grant in grants:
        set_override(api.owner, Person(member.user_id, org, "", "", "", "", ""), grant)
    set_scope(api.owner, member.user_id, org, companies=[UUID(fleet.north)])
    return member


# --- list and options ------------------------------------------------------------------


async def test_the_list_is_in_wire_order_with_allocations(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    body = cost(
        fleet,
        note="Stage fees",
        amount=1200,
        allocations=[
            {"vehicleId": fleet.kdb, "amount": 500},
            {"vehicleId": fleet.kda, "amount": 700},
        ],
    )
    parking = await create(api, owner, body)
    owner_savings = await create(api, owner, saving(fleet))
    response, count = await statements(api.client.get("/setup/recurring", headers=owner.headers))
    page = ok(response)
    assert count == 2
    assert list(page) == ["items", "pageNumber", "pageSize", "total"]
    assert (page["pageNumber"], page["pageSize"], page["total"]) == (1, 25, 2)
    assert [list(r) for r in page["items"]] == [RECURRING_KEYS, RECURRING_KEYS]
    savings_row, cost_row = page["items"]
    assert UUID(cost_row.pop("versionId"))
    assert cost_row == {
        "id": parking,
        "revision": 1,
        "name": "Parking",
        "kind": 1,
        "amount": 1200,
        "frequency": 2,
        "day": 5,
        "lastDay": False,
        "start": "2026-10-01",
        "end": None,
        "stoppedFrom": None,
        "allocations": [
            {"vehicleId": fleet.kda, "amount": 700, "registration": "KDA 482M", "active": True},
            {"vehicleId": fleet.kdb, "amount": 500, "registration": "KDB 111A", "active": True},
        ],
        "partial": False,
        "expenseItemId": fleet.parking,
        "expenseItemName": "Parking",
        "bucket": 2,
        "note": "Stage fees",
        "month": None,
        "activeAmount": 1200,
        "pausedFrom": None,
        "lastRun": None,
        "lastRunVehicles": 0,
        "balance": None,
        "lastRunStates": None,
        "condition": None,
        "opening": None,
        "nextRun": "2026-10-09",
    }
    assert [list(a) for a in cost_row["allocations"]] == [ALLOCATION_KEYS] * 2
    assert (savings_row["id"], savings_row["name"], savings_row["kind"]) == (
        owner_savings,
        "Owner savings",
        2,
    )
    assert (
        savings_row["bucket"],
        savings_row["expenseItemId"],
        savings_row["expenseItemName"],
        savings_row["note"],
    ) == (None, None, None, None)


async def test_a_yearly_item_lists_its_month_and_a_last_day_has_no_day(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    yearly = await create(api, owner, cost(fleet, frequency=4, day=10, month=3))
    monthly = await create(
        api, owner, saving(fleet, name="Fund", frequency=3, day=None, lastDay=True)
    )
    first = await row(api, owner, yearly)
    assert (first["frequency"], first["month"], first["day"], first["lastDay"]) == (4, 3, 10, False)
    second = await row(api, owner, monthly)
    assert (second["frequency"], second["month"], second["day"], second["lastDay"]) == (
        3,
        None,
        None,
        True,
    )


async def test_retired_shares_stay_in_the_total_and_the_active_amount_says_what_still_posts(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    body = cost(
        fleet,
        allocations=[
            {"vehicleId": fleet.kda, "amount": 700},
            {"vehicleId": fleet.kdb, "amount": 500},
        ],
    )
    item = await create(api, owner, body)
    ok(
        await api.client.post(
            f"/setup/vehicles/{fleet.kdb}/retire",
            json={"leftOn": "2026-10-07"},
            headers=owner.headers,
        )
    )
    found = await row(api, owner, item)
    assert (found["amount"], found["activeAmount"], found["partial"]) == (1200, 700, False)
    assert [(a["registration"], a["active"]) for a in found["allocations"]] == [
        ("KDA 482M", True),
        ("KDB 111A", False),
    ]


async def test_a_scoped_viewer_sees_only_its_shares_and_that_the_item_reaches_further(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    shared = await create(
        api,
        owner,
        saving(
            fleet,
            name="Office rent",
            amount=1200,
            allocations=[
                {"vehicleId": fleet.kda, "amount": 500},
                {"vehicleId": fleet.kdc, "amount": 700},
            ],
        ),
    )
    await create(
        api,
        owner,
        saving(
            fleet,
            name="Hidden",
            amount=900,
            allocations=[{"vehicleId": fleet.kdc, "amount": 900}],
        ),
    )
    sam = await scoped(api, fleet, "scheduled.view", "savings.view")
    listed = await rows(api, sam)
    (found,) = listed
    assert (found["id"], found["name"], found["partial"]) == (shared, "Office rent", True)
    assert (found["amount"], found["activeAmount"]) == (500, 500)
    assert found["allocations"] == [
        {"vehicleId": fleet.kda, "amount": 500, "registration": "KDA 482M", "active": True}
    ]
    whole = await row(api, owner, shared)
    assert (whole["amount"], whole["partial"], len(whole["allocations"])) == (1200, False, 2)


async def test_the_list_pages_after_ordering_by_name(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    for name in ("Charlie", "Alpha", "Bravo"):
        await create(api, owner, saving(fleet, name=name))
    page = ok(await api.client.get("/setup/recurring?page=2&pageSize=1", headers=owner.headers))
    assert (page["pageNumber"], page["pageSize"], page["total"]) == (2, 1, 3)
    assert [r["name"] for r in page["items"]] == ["Bravo"]


async def test_the_list_refuses_a_page_out_of_range_and_needs_a_view_right(
    api: AuthApi, owner: Member
) -> None:
    for query in ("page=0", "pageSize=101", "page=100001", "pageSize=0"):
        problem(
            await api.client.get(f"/setup/recurring?{query}", headers=owner.headers),
            400,
            INVALID,
            PAGING,
        )
    assert (
        await api.client.get("/setup/recurring?page=one", headers=owner.headers)
    ).status_code == 400
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    problem(await api.client.get("/setup/recurring", headers=clerk.headers), 403, FORBIDDEN)


async def test_the_list_filters_by_kind_company_and_status_with_running_items_first(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    parked = await create(api, owner, cost(fleet))
    south = [{"vehicleId": fleet.kdc, "amount": 1000}]
    zebra = await create(api, owner, saving(fleet, name="Zebra savings", allocations=south))
    spares = await create(
        api,
        owner,
        cost(
            fleet,
            amount=1000,
            allocations=south,
            expenseItemId=fleet.spares,
        ),
    )
    stopped = await api.client.post(
        f"/setup/recurring/{spares}/stop",
        json={"confirmed": True, "reason": "No longer needed"},
        headers=owner.headers,
    )
    ok(stopped)

    async def ids(query: str) -> list[str]:
        page = ok(await api.client.get(f"/setup/recurring{query}", headers=owner.headers))
        return [r["id"] for r in page["items"]]

    assert await ids(f"?companyId={fleet.north}") == [parked]
    assert await ids(f"?companyId={fleet.south}") == [zebra, spares]
    assert await ids(f"?companyId={fleet.south}&status=running") == [zebra]
    assert await ids(f"?companyId={fleet.south}&status=stopped") == [spares]
    assert await ids(f"?companyId={fleet.south}&kind=cost") == [spares]
    assert await ids(f"?companyId={fleet.south}&kind=savings") == [zebra]
    assert await ids("?kind=all&status=") == [parked, zebra, spares]
    assert await ids(f"?companyId={UNKNOWN}") == []
    response, count = await statements(
        api.client.get(
            f"/setup/recurring?companyId={fleet.south}&pageSize=1&page=2", headers=owner.headers
        )
    )
    page = ok(response)
    assert count == 2
    assert (page["total"], [r["id"] for r in page["items"]]) == (2, [spares])


async def test_a_filter_outside_its_choices_is_refused_before_the_permission_and_the_page(
    api: AuthApi, owner: Member
) -> None:
    for query, detail in (
        ("kind=fuel", KIND_FILTER),
        ("kind=Cost", KIND_FILTER),
        ("status=paused", STATUS_FILTER),
        ("kind=fuel&status=paused", KIND_FILTER),
        ("status=paused&page=0", STATUS_FILTER),
        ("kind=%00", UNSTORABLE),
    ):
        problem(
            await api.client.get(f"/setup/recurring?{query}", headers=owner.headers),
            400,
            INVALID,
            detail,
        )
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    problem(
        await api.client.get("/setup/recurring?kind=fuel", headers=clerk.headers),
        400,
        INVALID,
        KIND_FILTER,
    )
    malformed = await api.client.get("/setup/recurring?companyId=south", headers=owner.headers)
    assert malformed.status_code == 400


async def test_the_vehicle_options_offer_only_vehicles_a_new_share_can_use(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    ok(
        await api.client.post(
            f"/setup/vehicles/{fleet.kdb}/retire",
            json={"leftOn": "2026-10-07"},
            headers=owner.headers,
        )
    )
    old = await post_id(api, owner, "/setup/companies", {"name": "Old Line"})
    body = {
        "companyId": old,
        "registration": "KDG 600F",
        "fleetNumber": "OL-1",
        "joinedOn": "2026-10-01",
        "dayTargets": [1] * 7,
    }
    kdg = await post_id(api, owner, "/setup/vehicles", body)
    ok(
        await api.client.post(
            f"/setup/vehicles/{kdg}/retire", json={"leftOn": "2026-10-07"}, headers=owner.headers
        )
    )
    ok(await api.client.post(f"/setup/companies/{old}/archive", json={}, headers=owner.headers))
    response, count = await statements(
        api.client.get("/setup/recurring/vehicle-options", headers=owner.headers)
    )
    options = ok(response)
    assert count == 2
    assert [list(option) for option in options] == [OPTION_KEYS, OPTION_KEYS]
    assert options == [
        {
            "id": fleet.kda,
            "companyId": fleet.north,
            "companyName": "North Star",
            "registration": "KDA 482M",
            "active": True,
            "fleetNumber": "482M",
        },
        {
            "id": fleet.kdc,
            "companyId": fleet.south,
            "companyName": "South Line",
            "registration": "KDC 200B",
            "active": True,
            "fleetNumber": "200B",
        },
    ]
    sam = await scoped(
        api,
        fleet,
        "scheduled.view",
        "scheduled.add",
        "scheduled.edit",
        "savings.view",
        "savings.add",
        "savings.edit",
    )
    reach = ok(await api.client.get("/setup/recurring/vehicle-options", headers=sam.headers))
    assert [option["registration"] for option in reach] == ["KDA 482M"]


# --- create ----------------------------------------------------------------------------


async def test_a_cost_is_named_after_its_expense_item_and_logged_with_its_snapshot(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    response, count = await statements(
        api.client.post(
            "/setup/recurring", json=cost(fleet, note="  Stage fees  "), headers=owner.headers
        )
    )
    created = ok(response)
    assert count == 2
    assert list(created) == ["id"]
    listed = await row(api, owner, created["id"])
    assert (listed["name"], listed["bucket"], listed["note"]) == ("Parking", 2, "Stage fees")
    (entry,) = await entries(api, owner)
    assert list(entry) == ENTRY_KEYS
    assert (entry["section"], entry["entityId"]) == ("recurring", created["id"])
    assert (entry["reason"], entry["before"]) == ("Scheduled expense, Parking", "null")
    assert entry["actorName"] == "Jane Doe"
    assert entry["after"] == (
        f'{{"Id":"{created["id"]}","StoppedFrom":null,"PausedFrom":null,"Pauses":[],'
        f'"Versions":[{{"Id":"{listed["versionId"]}",'
        '"Revision":1,"EffectiveFrom":"2026-10-01","Name":"Parking","Kind":1,"Amount":1200,'
        '"Frequency":2,"Day":5,"LastDay":false,"Month":null,"Start":"2026-10-01","End":null,'
        f'"ExpenseItemId":"{fleet.parking}","Bucket":2,"Note":"Stage fees",'
        f'"Allocations":[{{"VehicleId":"{fleet.kda}","Amount":1200}}],'
        '"ConditionMin":null,"ConditionDays":null}],"Opening":null}'
    )


async def test_a_saving_keeps_its_typed_name_and_a_typed_reason_follows(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(
        api,
        owner,
        saving(fleet, name=" Owner savings ", reason="Put money aside for the owner."),
    )
    listed = await row(api, owner, item)
    assert (listed["name"], listed["kind"], listed["bucket"]) == ("Owner savings", 2, None)
    assert await reasons(api, owner) == [
        "Saving, Owner savings. Reason: Put money aside for the owner."
    ]


async def test_a_cost_takes_its_bucket_from_the_category_of_its_item(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    spares = await create(api, owner, cost(fleet, expenseItemId=fleet.spares, note="n" * 200))
    repayment = await create(api, owner, cost(fleet, expenseItemId=fleet.repayment))
    first = await row(api, owner, spares)
    second = await row(api, owner, repayment)
    assert (first["name"], first["bucket"], len(first["note"])) == ("Spares", 1, 200)
    assert (second["name"], second["bucket"]) == ("Loan repayment", 3)


async def test_an_older_body_with_a_category_is_read_and_the_field_ignored(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(api, owner, saving(fleet, category="Charges"))
    assert (await row(api, owner, item))["name"] == "Owner savings"


async def test_the_save_is_refused_with_the_sentence_of_the_first_failing_step(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    two_shares = [{"vehicleId": fleet.kda, "amount": 600}, {"vehicleId": fleet.kdb, "amount": 300}]
    same_vehicle = [{"vehicleId": fleet.kda, "amount": 500}] * 2
    cases: list[tuple[dict[str, Any], str]] = [
        (saving(fleet, reason="x" * 501), REASON_LENGTH),
        (saving(fleet, expenseItemId=fleet.parking), "Savings must not have an expense item."),
        (cost(fleet, expenseItemId=UNKNOWN), "Choose an expense item that is in use."),
        (cost(fleet, day=7), SHAPE),
        (cost(fleet, frequency=4, day=10), SHAPE),
        (cost(fleet, frequency=4, day=10, month=13), SHAPE),
        (cost(fleet, frequency=3, day=10, month=3), SHAPE),
        (cost(fleet, frequency=9, day=1), SHAPE),
        (saving(fleet, name="  "), "Name must contain 1-160 characters."),
        (saving(fleet, name="x" * 161), "Name must contain 1-160 characters."),
        (saving(fleet, amount=0), MONEY),
        (saving(fleet, kind=3), "Costs need an expense item; savings must not have one."),
        (saving(fleet, note="n" * 201), "A note can have at most 200 characters."),
        (saving(fleet, end="2026-10-06"), "End date must be on or after start date."),
        (saving(fleet, allocations=[]), "Choose 1-500 distinct vehicles."),
        (saving(fleet, allocations=same_vehicle), "Choose 1-500 distinct vehicles."),
        (
            saving(fleet, allocations=[{"vehicleId": fleet.kda, "amount": 0}]),
            MONEY,
        ),
        (
            saving(fleet, allocations=two_shares),
            "Vehicle shares must equal the total exactly.",
        ),
        (
            cost(fleet, frequency=1, day=None),
            "Daily schedules are no longer offered. Choose weekly, monthly or yearly.",
        ),
        (
            saving(fleet, frequency=4, day=10, month=3, end="2026-12-31"),
            "A saving has no end date.",
        ),
        (
            cost(fleet, expenseItemId=None),
            "Choose the expense item this cost is for.",
        ),
        (cost(fleet, start=None), "Start date is required."),
        (
            cost(fleet, start="2026-09-30"),
            "A schedule can start no earlier than the first of the current month.",
        ),
    ]
    for body, detail in cases:
        response = await api.client.post("/setup/recurring", json=body, headers=owner.headers)
        problem(response, 400, INVALID, detail)
    assert await entries(api, owner) == []


async def test_a_new_share_needs_a_vehicle_in_reach_in_the_fleet_and_in_a_company_in_use(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    ok(
        await api.client.post(
            f"/setup/vehicles/{fleet.kdb}/retire",
            json={"leftOn": "2026-10-07"},
            headers=owner.headers,
        )
    )
    only = [{"vehicleId": fleet.kdb, "amount": 1000}]
    problem(
        await api.client.post(
            "/setup/recurring", json=saving(fleet, allocations=only), headers=owner.headers
        ),
        400,
        INVALID,
        "New recurring shares must use active vehicles and companies.",
    )
    unknown = [{"vehicleId": UNKNOWN, "amount": 1000}]
    problem(
        await api.client.post(
            "/setup/recurring", json=saving(fleet, allocations=unknown), headers=owner.headers
        ),
        404,
        NOT_FOUND,
    )
    sam = await scoped(
        api,
        fleet,
        "scheduled.view",
        "scheduled.add",
        "scheduled.edit",
        "savings.view",
        "savings.add",
        "savings.edit",
    )
    outside = [{"vehicleId": fleet.kda, "amount": 500}, {"vehicleId": fleet.kdc, "amount": 500}]
    problem(
        await api.client.post(
            "/setup/recurring", json=saving(fleet, allocations=outside), headers=sam.headers
        ),
        404,
        NOT_FOUND,
    )
    inside = [{"vehicleId": fleet.kda, "amount": 1000}]
    await create(api, sam, saving(fleet, allocations=inside))


async def test_an_expense_item_that_is_turned_off_is_refused(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    ok(await api.client.post(f"/setup/expense-items/{fleet.parking}/stop", headers=owner.headers))
    problem(
        await api.client.post("/setup/recurring", json=cost(fleet), headers=owner.headers),
        400,
        INVALID,
        "Choose an expense item that is in use.",
    )


# --- revise ----------------------------------------------------------------------------


async def test_a_revise_names_what_changed_with_one_two_and_three_parts(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(api, owner, cost(fleet))
    one = cost(fleet, note="Stage fees")
    response, count = await statements(
        api.client.put(f"/setup/recurring/{item}", json=one, headers=owner.headers)
    )
    assert ok(response) == {"id": item}
    assert count == 2
    two = cost(
        fleet,
        note="Stage fees",
        amount=1500,
        allocations=[
            {"vehicleId": fleet.kda, "amount": 1000},
            {"vehicleId": fleet.kdb, "amount": 500},
        ],
    )
    assert await revise(api, owner, item, two) == {"id": item}
    three = {**two, "day": None, "frequency": 3, "lastDay": True, "end": "2026-12-31", "note": None}
    assert await revise(api, owner, item, three) == {"id": item}
    assert await reasons(api, owner) == [
        "Scheduled expense, Parking",
        "Scheduled expense, Parking",
        "Scheduled expense, Parking",
        "Scheduled expense, Parking",
    ]
    log = (await entries(api, owner))[1]
    assert (log["section"], log["entityId"]) == ("recurring", item)
    before, after = json.loads(log["before"]), json.loads(log["after"])
    assert [v["Revision"] for v in before["Versions"]] == [1, 2]
    assert [v["Revision"] for v in after["Versions"]] == [1, 2, 3]
    final = await row(api, owner, item)
    assert (final["revision"], final["amount"], final["frequency"], final["lastDay"]) == (
        4,
        1500,
        3,
        True,
    )
    assert (final["day"], final["end"], final["note"]) == (None, "2026-12-31", None)


async def test_a_typed_reason_follows_the_change_sentence(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(api, owner, saving(fleet))
    await revise(
        api,
        owner,
        item,
        saving(
            fleet,
            amount=1100,
            allocations=[{"vehicleId": fleet.kda, "amount": 1100}],
            reason="Raised",
        ),
    )
    assert (await reasons(api, owner))[-1] == ("Saving, Owner savings. Reason: Raised.")


async def test_a_revise_that_changes_nothing_is_ok_and_leaves_no_history(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(api, owner, cost(fleet, note="Stage fees"))
    before = await entries(api, owner)
    again = cost(fleet, name="Ignored for costs", note=" Stage fees ")
    response, count = await statements(
        api.client.put(f"/setup/recurring/{item}", json=again, headers=owner.headers)
    )
    assert ok(response) == {"id": item}
    assert count == 2
    assert await entries(api, owner) == before
    assert (await row(api, owner, item))["revision"] == 1


async def test_a_revise_is_refused_for_the_same_reasons_as_a_create(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(api, owner, saving(fleet))
    path = f"/setup/recurring/{item}"
    problem(
        await api.client.put(path, json=saving(fleet, amount=0), headers=owner.headers),
        400,
        INVALID,
        MONEY,
    )
    problem(
        await api.client.put(path, json=saving(fleet, day=9), headers=owner.headers),
        400,
        INVALID,
        SHAPE,
    )
    problem(
        await api.client.put(path, json=saving(fleet, reason="x" * 501), headers=owner.headers),
        400,
        INVALID,
        REASON_LENGTH,
    )


async def test_an_unknown_item_cannot_be_revised(api: AuthApi, owner: Member, fleet: Fleet) -> None:
    problem(
        await api.client.put(
            f"/setup/recurring/{UNKNOWN}", json=saving(fleet), headers=owner.headers
        ),
        404,
        NOT_FOUND,
    )


async def test_a_running_item_keeps_its_start_date(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(api, owner, cost(fleet, start="2026-10-01"))
    problem(
        await api.client.put(
            f"/setup/recurring/{item}", json=cost(fleet, start="2026-10-03"), headers=owner.headers
        ),
        400,
        INVALID,
        "An already running item's start date cannot change.",
    )
    assert await revise(api, owner, item, cost(fleet, start="2026-10-01", day=0)) == {"id": item}


async def test_a_pending_item_can_move_its_start_but_not_before_the_month(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    pending = await create(api, owner, cost(fleet, start="2026-10-20"))
    path = f"/setup/recurring/{pending}"
    problem(
        await api.client.put(path, json=cost(fleet, start="2026-09-20"), headers=owner.headers),
        400,
        INVALID,
        "A schedule can start no earlier than the first of the current month.",
    )
    assert await revise(api, owner, pending, cost(fleet, start="2026-10-12")) == {"id": pending}
    assert (await row(api, owner, pending))["start"] == "2026-10-12"


async def test_a_stopped_item_cannot_be_edited(api: AuthApi, owner: Member, fleet: Fleet) -> None:
    item = await create(api, owner, saving(fleet))
    ok(
        await api.client.post(
            f"/setup/recurring/{item}/stop",
            json={"confirmed": True, "reason": "Ended"},
            headers=owner.headers,
        )
    )
    problem(
        await api.client.put(
            f"/setup/recurring/{item}",
            json=saving(fleet, amount=900, allocations=[{"vehicleId": fleet.kda, "amount": 900}]),
            headers=owner.headers,
        ),
        400,
        INVALID,
        "Stopped items cannot be edited.",
    )


async def test_an_item_reaching_beyond_the_scope_cannot_be_changed_by_a_scoped_manager(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    body = saving(
        fleet,
        allocations=[
            {"vehicleId": fleet.kda, "amount": 500},
            {"vehicleId": fleet.kdc, "amount": 500},
        ],
    )
    wide = await create(api, owner, body)
    hidden = await create(
        api, owner, saving(fleet, allocations=[{"vehicleId": fleet.kdc, "amount": 1000}])
    )
    sam = await scoped(
        api,
        fleet,
        "scheduled.view",
        "scheduled.add",
        "scheduled.edit",
        "savings.view",
        "savings.add",
        "savings.edit",
    )
    inside = saving(fleet, allocations=[{"vehicleId": fleet.kda, "amount": 1000}])
    problem(
        await api.client.put(f"/setup/recurring/{wide}", json=inside, headers=sam.headers),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.post(
            f"/setup/recurring/{wide}/stop",
            json={"confirmed": True, "reason": "Ended"},
            headers=sam.headers,
        ),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.post(f"/setup/recurring/{wide}/restore", headers=sam.headers),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.put(f"/setup/recurring/{hidden}", json=inside, headers=sam.headers),
        404,
        NOT_FOUND,
    )


# --- stop and restore ------------------------------------------------------------------


async def test_a_stop_takes_effect_today_and_repeating_it_is_ok(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(api, owner, cost(fleet))
    path = f"/setup/recurring/{item}/stop"
    body = {"confirmed": True, "reason": "Parking moved into the SACCO fee"}
    response, count = await statements(api.client.post(path, json=body, headers=owner.headers))
    assert ok(response) == {"id": item}
    assert count == 2
    assert (await row(api, owner, item))["stoppedFrom"] == "2026-10-07"
    entry = (await entries(api, owner))[0]
    assert (
        entry["reason"] == "Scheduled expense, Parking. Reason: Parking moved into the SACCO fee."
    )
    assert (entry["section"], entry["entityId"]) == ("recurring", item)
    assert json.loads(entry["before"])["StoppedFrom"] is None
    assert json.loads(entry["after"])["StoppedFrom"] == "2026-10-07"
    again = await api.client.post(path, json={**body, "reason": "Again"}, headers=owner.headers)
    assert ok(again) == {"id": item}
    assert len(await entries(api, owner)) == 2


async def test_stopping_needs_a_reason_and_a_confirmation_before_anything_else(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(api, owner, cost(fleet))
    for body in ({}, {"confirmed": True}, {"confirmed": True, "reason": "  "}):
        problem(
            await api.client.post(
                f"/setup/recurring/{item}/stop", json=body, headers=owner.headers
            ),
            400,
            INVALID,
            REASON_LENGTH,
        )
    problem(
        await api.client.post(
            f"/setup/recurring/{item}/stop",
            json={"confirmed": True, "reason": "x" * 501},
            headers=owner.headers,
        ),
        400,
        INVALID,
        REASON_LENGTH,
    )
    for body in ({"reason": "Ended"}, {"confirmed": False, "reason": "Ended"}):
        problem(
            await api.client.post(
                f"/setup/recurring/{item}/stop", json=body, headers=owner.headers
            ),
            400,
            INVALID,
            STOP_CONFIRM,
        )
    problem(
        await api.client.post(
            f"/setup/recurring/{UNKNOWN}/stop",
            json={"confirmed": True, "reason": "Ended"},
            headers=owner.headers,
        ),
        404,
        NOT_FOUND,
    )
    problem(
        await api.client.post(
            f"/setup/recurring/{UNKNOWN}/stop", json={"reason": "Ended"}, headers=owner.headers
        ),
        400,
        INVALID,
        STOP_CONFIRM,
    )
    assert (await row(api, owner, item))["stoppedFrom"] is None


@pytest.mark.parametrize(
    ("day", "detail"),
    [
        (
            date(2026, 10, 12),
            "This item is already due to stop on a later date. Cancel that stop first.",
        ),
        (date(2026, 10, 2), "The item is already stopped."),
    ],
)
async def test_a_stop_on_another_date_is_never_re_dated(
    api: AuthApi, owner: Member, fleet: Fleet, day: date, detail: str
) -> None:
    item = await create(api, owner, cost(fleet))
    stopped_from(api, item, day)
    problem(
        await api.client.post(
            f"/setup/recurring/{item}/stop",
            json={"confirmed": True, "reason": "Ended"},
            headers=owner.headers,
        ),
        400,
        INVALID,
        detail,
    )


async def test_cancelling_a_later_stop_reads_no_body(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(api, owner, cost(fleet))
    path = f"/setup/recurring/{item}/restore"
    before = await entries(api, owner)
    response, count = await statements(api.client.post(path, headers=owner.headers))
    assert ok(response) == {"id": item}
    assert count == 2
    assert await entries(api, owner) == before
    stopped_from(api, item, date(2026, 10, 12))
    cancelled = await api.client.post(path, content=b"ignored", headers=owner.headers)
    assert ok(cancelled) == {"id": item}
    assert (await row(api, owner, item))["stoppedFrom"] is None
    entry = (await entries(api, owner))[0]
    assert entry["reason"] == "Scheduled expense, Parking"
    assert json.loads(entry["before"])["StoppedFrom"] == "2026-10-12"
    assert json.loads(entry["after"])["StoppedFrom"] is None


async def test_a_stop_in_effect_cannot_be_cancelled(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(api, owner, cost(fleet))
    ok(
        await api.client.post(
            f"/setup/recurring/{item}/stop",
            json={"confirmed": True, "reason": "Ended"},
            headers=owner.headers,
        )
    )
    problem(
        await api.client.post(f"/setup/recurring/{item}/restore", headers=owner.headers),
        400,
        INVALID,
        "This item has already stopped. Add a new scheduled item instead.",
    )
    problem(
        await api.client.post(f"/setup/recurring/{UNKNOWN}/restore", headers=owner.headers),
        404,
        NOT_FOUND,
    )


# --- bodies, permissions and tokens ----------------------------------------------------


async def test_body_routes_require_a_json_body(api: AuthApi, owner: Member, fleet: Fleet) -> None:
    item = await create(api, owner, cost(fleet))
    payload = json.dumps(saving(fleet)).encode()
    text = {**owner.headers, "Content-Type": "text/plain"}
    for method, path in [
        ("POST", "/setup/recurring"),
        ("PUT", f"/setup/recurring/{item}"),
        ("POST", f"/setup/recurring/{item}/stop"),
    ]:
        empty(await api.client.request(method, path, content=payload, headers=text), 415)
        empty(await api.client.request(method, path, content=payload, headers=owner.headers), 415)
    empty(await api.client.post(f"/setup/recurring/{item}/stop", headers=owner.headers), 415)
    malformed = await api.client.post(
        "/setup/recurring",
        content=b"{not json",
        headers={**owner.headers, "Content-Type": "application/json"},
    )
    assert malformed.status_code == 400
    assert len(await entries(api, owner)) == 1


async def test_a_malformed_item_id_is_an_empty_not_found(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    empty(
        await api.client.put(
            "/setup/recurring/not-a-uuid", json=saving(fleet), headers=owner.headers
        ),
        404,
    )
    empty(
        await api.client.post(
            "/setup/recurring/not-a-uuid/stop",
            json={"confirmed": True, "reason": "Ended"},
            headers=owner.headers,
        ),
        404,
    )
    empty(await api.client.post("/setup/recurring/not-a-uuid/restore", headers=owner.headers), 404)


async def test_recurring_routes_need_their_permissions(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = await create(api, owner, cost(fleet))
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    problem(await api.client.get("/setup/recurring", headers=clerk.headers), 403, FORBIDDEN)
    problem(
        await api.client.get("/setup/recurring/vehicle-options", headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.post("/setup/recurring", json=saving(fleet), headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.put(f"/setup/recurring/{item}", json=saving(fleet), headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.post(
            f"/setup/recurring/{item}/stop",
            json={"confirmed": True, "reason": "Ended"},
            headers=clerk.headers,
        ),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.post(f"/setup/recurring/{item}/restore", headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    viewer = await scoped(api, fleet, "scheduled.view", "savings.view")
    assert (await api.client.get("/setup/recurring", headers=viewer.headers)).status_code == 200
    problem(
        await api.client.get("/setup/recurring/vehicle-options", headers=viewer.headers),
        403,
        FORBIDDEN,
    )
    assert len(await entries(api, owner)) == 1


async def test_recurring_routes_need_a_token(api: AuthApi, owner: Member, fleet: Fleet) -> None:
    item = await create(api, owner, cost(fleet))
    empty(await api.client.get("/setup/recurring"), 401)
    empty(await api.client.get("/setup/recurring/vehicle-options"), 401)
    empty(await api.client.post("/setup/recurring", json=saving(fleet)), 401)
    empty(await api.client.put(f"/setup/recurring/{item}", json=saving(fleet)), 401)
    empty(
        await api.client.post(
            f"/setup/recurring/{item}/stop", json={"confirmed": True, "reason": "Ended"}
        ),
        401,
    )
    empty(await api.client.post(f"/setup/recurring/{item}/restore"), 401)
