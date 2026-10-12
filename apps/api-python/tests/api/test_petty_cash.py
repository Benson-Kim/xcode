"""The petty-cash routes against the real database (``docs/06-http-contract.md`` section
2.11): every route's answer in wire order, a create answering 200 and replaying by its id,
the comma lists of the entry filters, the 409 with ``current`` (the entry as the list serves
it, or null), the float guard's 400 with ``balanceAfter``, the back-dating 400 with
``earliest``, amounts read exactly, the route constraints, 401, 415 and the statement budget
of 2.

The business date is 7 Oct 2026, a Wednesday (the test clock in Nairobi); weeks start on
Monday. Wanjiru Kamau keeps a float (Fleet manager), Peter Otieno reviews (Office admin with
the reviewing rights, approval limit 5000); the fleet and the expense catalogue are seeded
as ``xcode_owner``."""

from __future__ import annotations

import re
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest

from xcode_api.http.messages import MESSAGES
from xcode_api.http.routers.pettycash import router

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
from ..support.setup_rows import add_category, add_item
from ..support.tenancy import Member as Person
from ..support.tenancy import add_company, add_vehicle, set_override, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

TODAY = "2026-10-07"
SAVED_KEYS = ["id", "version", "status", "balance"]
APPROVED_KEYS = ["approved", "total", "skipped"]
OVERVIEW_KEYS = [
    "businessDate",
    "date",
    "period",
    "from",
    "to",
    "permissions",
    "holders",
    "figures",
    "floats",
]
PERMISSION_KEYS = [
    "holderId",
    "canSpend",
    "canViewAll",
    "canIssue",
    "canIssueNegative",
    "canApproveItem",
    "canApproveDay",
    "approvalLimit",
    "canView",
    "canSpendOther",
    "canEditOwn",
    "canEdit",
    "canDeleteOwn",
    "canDelete",
    "canDeleteApproved",
    "canSendBack",
    "canReject",
    "canReopen",
    "canCredit",
    "canDeleteCash",
    "earliestDate",
]
FIGURE_KEYS = [
    "openingBalance",
    "cashReceived",
    "expenses",
    "creditNotes",
    "moneyOut",
    "closingBalance",
    "waiting",
    "waitingCount",
]
FLOAT_KEYS = [
    "holderId",
    "name",
    "active",
    "cashReceived",
    "creditNotes",
    "expenses",
    "waiting",
    "waitingCount",
    "approved",
    "sentBack",
    "balance",
    "lastCashOn",
    "rejected",
]
ENTRY_KEYS = [
    "id",
    "kind",
    "holderId",
    "holderName",
    "date",
    "vehicleId",
    "registration",
    "expenseItemId",
    "expenseItemName",
    "bucket",
    "units",
    "unitAmount",
    "total",
    "payee",
    "note",
    "reimbursable",
    "status",
    "sentBackNote",
    "reviewedByName",
    "reviewedAt",
    "recordedByName",
    "recordedAt",
    "updatedAt",
    "version",
    "canEdit",
    "canRemove",
    "canReview",
    "aboveLimit",
    "rejectReason",
    "reopenReason",
    "canSendBack",
    "canReject",
    "canReopen",
]
CHANGED = "This entry has changed."
INSTANT = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00$")
REVIEWER_RIGHTS = (
    "pettycash.view",
    "pettycash.view_all",
    "pettycash.issue",
    "pettycash.credit",
    "pettycash.approve_item",
    "pettycash.approve_day",
    "pettycash.send_back",
    "pettycash.reject",
    "pettycash.reopen",
    "pettycash.delete",
    "pettycash.delete_approved",
    "pettycash.delete_cash",
    "dash.pettycash",
)


@dataclass(frozen=True)
class Yard:
    api: AuthApi
    org: UUID
    owner: Member
    clerk: Member
    reviewer: Member
    vehicle: str
    item: str


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
async def yard(api: AuthApi) -> Yard:
    owner = await _person(api, None, "Owner", "0711000111", "Antony Maina")
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    org = UUID(str(row["id"]))
    set_scope(api.owner, owner.user_id, org, all_companies=True)
    clerk = await _person(api, org, "Fleet manager", "0722000111", "Wanjiru Kamau")
    reviewer = await _person(api, org, "Office admin", "0733000111", "Peter Otieno")
    who = Person(reviewer.user_id, org, "", "", "", "", "")
    for right in REVIEWER_RIGHTS:
        set_override(api.owner, who, right)
    api.owner.execute(
        "UPDATE tenancy.memberships SET approval_limit = 5000 WHERE user_id = %s",
        (reviewer.user_id,),
    )
    company = add_company(api.owner, org, "Petty Fleet")
    vehicle = add_vehicle(api.owner, org, company, "KAA 501A", joined_on=date(2026, 9, 1))
    item = add_item(api.owner, org, add_category(api.owner, org, "Repairs", bucket=1), "Tyres")
    return Yard(api, org, owner, clerk, reviewer, str(vehicle), str(item))


def post(yard: Yard, who: Member, path: str, body: Any) -> Any:
    return yard.api.client.post(f"/setup/pettycash{path}", json=body, headers=who.headers)


def get(yard: Yard, who: Member, path: str) -> Any:
    return yard.api.client.get(f"/setup/pettycash{path}", headers=who.headers)


def expense(yard: Yard, amount: Any = 300, **more: Any) -> dict[str, Any]:
    body = {
        "kind": "expense",
        "date": TODAY,
        "unitAmount": amount,
        "vehicleId": yard.vehicle,
        "expenseItemId": yard.item,
    }
    return {**body, **more}


async def cash(yard: Yard, amount: Any, **more: Any) -> Any:
    body = {
        "kind": "cash",
        "date": TODAY,
        "unitAmount": amount,
        "holderId": str(yard.clerk.user_id),
    }
    return ok(await post(yard, yard.owner, "/entries", {**body, **more}))


# --- writes ---------------------------------------------------------------------------------


async def test_a_create_answers_200_with_the_saved_entry_and_replays_by_its_id(
    yard: Yard,
) -> None:
    entry_id = str(uuid4())
    body = {"kind": "cash", "date": TODAY, "unitAmount": 1000, "id": entry_id}
    body["holderId"] = str(yard.clerk.user_id)
    response, count = await statements(post(yard, yard.owner, "/entries", body))
    saved = ok(response)
    assert count == 2
    assert list(saved) == SAVED_KEYS
    assert saved == {"id": entry_id, "version": 1, "status": None, "balance": 1000}
    assert (
        response.content
        == f'{{"id":"{entry_id}","version":1,"status":null,"balance":1000}}'.encode()
    )
    again = ok(await post(yard, yard.owner, "/entries", {**body, "unitAmount": 5}))
    assert again == saved
    taken = problem(
        await post(yard, yard.reviewer, "/entries", body),
        409,
        CHANGED,
        "This entry was already saved by someone else. Reload and try again.",
    )
    assert taken["current"] is None


async def test_an_expense_moves_through_review_on_the_wire(yard: Yard) -> None:
    await cash(yard, 1000)
    first = ok(await post(yard, yard.clerk, "/entries", expense(yard, 150, units=2)))
    assert (first["status"], first["balance"]) == ("waiting", 700)
    second = ok(await post(yard, yard.clerk, "/entries", expense(yard, "50.50")))
    assert second["balance"] == 649.5
    approved = ok(
        await post(yard, yard.reviewer, f"/entries/{first['id']}/approve", {"version": 1})
    )
    assert approved == {"id": first["id"], "version": 2, "status": "approved", "balance": 649.5}
    back = f"/entries/{second['id']}/send-back"
    sent = ok(await post(yard, yard.reviewer, back, {"version": 1, "comment": "Receipt?"}))
    assert sent["status"] == "sentBack"
    resubmitted = ok(
        await yard.api.client.put(
            f"/setup/pettycash/entries/{second['id']}",
            json=expense(yard, "50.50", version=2),
            headers=yard.clerk.headers,
        )
    )
    assert (resubmitted["version"], resubmitted["status"]) == (3, "waiting")
    rejected = ok(
        await post(
            yard, yard.reviewer, f"/entries/{second['id']}/reject", {"version": 3, "reason": "No"}
        )
    )
    assert (rejected["status"], rejected["balance"]) == ("rejected", 700)
    reopened = ok(
        await post(
            yard, yard.reviewer, f"/entries/{second['id']}/reopen", {"version": 4, "reason": "Yes"}
        )
    )
    assert (reopened["status"], reopened["balance"]) == ("waiting", 649.5)
    removed = ok(await post(yard, yard.reviewer, f"/entries/{second['id']}/remove", {"version": 5}))
    assert (removed["version"], removed["balance"]) == (6, 700)
    problem(
        await post(yard, yard.reviewer, f"/entries/{first['id']}/remove", {"version": 2}),
        400,
        INVALID,
        sentence("reason_length"),
    )


async def test_a_stale_version_is_a_409_with_the_entry_as_the_list_serves_it(
    yard: Yard,
) -> None:
    made = ok(await post(yard, yard.clerk, "/entries", expense(yard, note=" new tyres ")))
    body = problem(
        await post(yard, yard.reviewer, f"/entries/{made['id']}/approve", {"version": 9}),
        409,
        CHANGED,
        "This entry was changed after you opened it. Check it and save again.",
    )
    current = body["current"]
    assert list(current) == ENTRY_KEYS
    listed = ok(await get(yard, yard.reviewer, "/entries"))["items"]
    assert current == listed[0]
    assert (current["date"], current["note"], current["units"], current["total"]) == (
        TODAY,
        "new tyres",
        1,
        300,
    )
    assert (current["kind"], current["status"], current["bucket"]) == ("expense", "waiting", 1)
    assert (current["holderName"], current["registration"], current["expenseItemName"]) == (
        "Wanjiru Kamau",
        "KAA 501A",
        "Tyres",
    )
    assert INSTANT.match(current["recordedAt"])
    assert (current["canReview"], current["canEdit"], current["version"]) == (True, False, 1)
    missing = problem(
        await post(yard, yard.reviewer, f"/entries/{uuid4()}/approve", {"version": 1}),
        404,
        NOT_FOUND,
    )
    assert "current" not in missing


async def test_cash_taken_below_zero_is_a_400_with_the_balance_after(yard: Yard) -> None:
    await cash(yard, 100)
    body = {
        "kind": "cash",
        "date": TODAY,
        "unitAmount": "-150.25",
        "holderId": str(yard.clerk.user_id),
    }
    refused = problem(
        await post(yard, yard.reviewer, "/entries", body),
        400,
        INVALID,
        'This takes the float below zero, which needs the permission "Issue cash to a float'
        ' below zero".',
    )
    assert refused["balanceAfter"] == -50.25
    assert ok(await post(yard, yard.owner, "/entries", body))["balance"] == -50.25


async def test_a_day_before_the_back_dating_limit_is_a_400_with_the_earliest_day(
    yard: Yard,
) -> None:
    yard.api.owner.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = 'days', back_limit_count = 1 "
        "WHERE user_id = %s",
        (yard.clerk.user_id,),
    )
    refused = problem(
        await post(yard, yard.clerk, "/entries", expense(yard, date="2026-10-05")),
        400,
        INVALID,
        "You can only add or change records dated 2026-10-06 or later.",
    )
    assert refused["earliest"] == "2026-10-06"


async def test_amounts_and_units_are_read_exactly_and_checked_by_the_routine(
    yard: Yard,
) -> None:
    problem(
        await post(yard, yard.clerk, "/entries", expense(yard, "10.005")),
        400,
        INVALID,
        "Enter the amount with at most two decimals.",
    )
    problem(
        await post(yard, yard.clerk, "/entries", expense(yard, 10, units="0.0001")),
        400,
        INVALID,
        "Units must be above zero, with at most three decimals.",
    )
    response = await yard.api.client.post(
        "/setup/pettycash/entries",
        content=b'{"kind":"expense","date":"2026-10-07","unitAmount":"1e999999"}',
        headers={**yard.clerk.headers, "content-type": "application/json"},
    )
    assert list(problem(response, 400, INVALID, response.json().get("detail"))["errors"]) == [
        "unitAmount"
    ]
    response = await post(yard, yard.clerk, "/entries", {**expense(yard), "kind": 2})
    assert list(problem(response, 400, INVALID, response.json().get("detail"))["errors"]) == [
        "kind"
    ]


async def test_ticked_entries_and_a_day_are_approved_with_counts(yard: Yard) -> None:
    first = ok(await post(yard, yard.clerk, "/entries", expense(yard, 100)))
    second = ok(await post(yard, yard.clerk, "/entries", expense(yard, 6000)))
    third = ok(await post(yard, yard.clerk, "/entries", expense(yard, 40)))
    problem(
        await post(yard, yard.reviewer, "/approve", {"entries": []}),
        400,
        INVALID,
        "Choose the entries to approve.",
    )
    ticked = {"entries": [{"id": first["id"], "version": 1}, {"id": first["id"], "version": 7}]}
    response, count = await statements(post(yard, yard.reviewer, "/approve", ticked))
    answered = ok(response)
    assert count == 2
    assert list(answered) == APPROVED_KEYS
    assert answered == {"approved": 1, "total": 100, "skipped": 0}
    day = {"date": TODAY, "holderId": str(yard.clerk.user_id), "to": None}
    assert ok(await post(yard, yard.reviewer, "/approve-day", day)) == {
        "approved": 1,
        "total": 40,
        "skipped": 1,
    }
    listed = ok(await get(yard, yard.reviewer, "/entries?status=approved"))["items"]
    assert sorted(e["id"] for e in listed) == sorted([first["id"], third["id"]])
    assert second["status"] == "waiting"
    problem(await post(yard, yard.clerk, "/approve-day", day), 403, FORBIDDEN)


async def test_a_null_entries_list_asks_for_the_entries_as_an_empty_one_does(yard: Yard) -> None:
    for body in ({"entries": None}, {}):
        problem(
            await post(yard, yard.reviewer, "/approve", body),
            400,
            INVALID,
            "Choose the entries to approve.",
        )


async def test_every_route_keeps_the_statement_budget_of_two(yard: Yard) -> None:
    budget: dict[str, int] = {}

    async def spend(name: str, call: Awaitable[Any]) -> Any:
        response, budget[name] = await statements(call)
        return ok(response)

    holder = str(yard.clerk.user_id)
    given = {"kind": "cash", "date": TODAY, "unitAmount": 1000, "holderId": holder}
    await spend("give cash", post(yard, yard.owner, "/entries", given))
    first = await spend("create", post(yard, yard.clerk, "/entries", expense(yard, 300)))
    await spend(
        "change",
        yard.api.client.put(
            f"/setup/pettycash/entries/{first['id']}",
            json=expense(yard, 350, version=1),
            headers=yard.clerk.headers,
        ),
    )
    await spend(
        "approve", post(yard, yard.reviewer, f"/entries/{first['id']}/approve", {"version": 2})
    )
    second = ok(await post(yard, yard.clerk, "/entries", expense(yard, 20)))
    back = {"version": 1, "comment": "Receipt?"}
    await spend("send back", post(yard, yard.reviewer, f"/entries/{second['id']}/send-back", back))
    third = f"/entries/{ok(await post(yard, yard.clerk, '/entries', expense(yard, 30)))['id']}"
    await spend(
        "reject", post(yard, yard.reviewer, f"{third}/reject", {"version": 1, "reason": "No"})
    )
    await spend(
        "reopen", post(yard, yard.reviewer, f"{third}/reopen", {"version": 2, "reason": "Yes"})
    )
    await spend("remove", post(yard, yard.reviewer, f"{third}/remove", {"version": 3}))
    fourth = ok(await post(yard, yard.clerk, "/entries", expense(yard, 40)))
    ticked = {"entries": [{"id": fourth["id"], "version": 1}]}
    await spend("approve ticked", post(yard, yard.reviewer, "/approve", ticked))
    day = {"date": TODAY, "holderId": holder}
    await spend("approve day", post(yard, yard.reviewer, "/approve-day", day))
    for path in ("/overview", "/entries", "/options"):
        await spend(path, get(yard, yard.clerk, path))
    await spend("/dashboard", get(yard, yard.reviewer, "/dashboard"))
    assert len(budget) == 14
    assert budget == dict.fromkeys(budget, 2)


async def test_an_approved_expense_reaches_the_vehicle_report_and_a_credit_note_never(
    yard: Yard,
) -> None:
    await cash(yard, 1000)
    spent = ok(await post(yard, yard.clerk, "/entries", expense(yard, 300)))
    credit = {"kind": "credit", "date": TODAY, "unitAmount": 100, "note": "Change returned"}
    ok(await post(yard, yard.owner, "/entries", {**credit, "holderId": str(yard.clerk.user_id)}))

    async def report() -> Any:
        return ok(
            await yard.api.client.get(
                f"/setup/vehicles/{yard.vehicle}/report?period=week", headers=yard.owner.headers
            )
        )

    before = await report()
    assert [p for p in before["postings"] if p["source"] == "pettycash"] == []
    ok(await post(yard, yard.reviewer, f"/entries/{spent['id']}/approve", {"version": 1}))
    after = await report()
    assert [p for p in after["postings"] if p["source"] == "pettycash"] == [
        {
            "itemId": spent["id"],
            "versionId": spent["id"],
            "date": TODAY,
            "name": "Tyres",
            "kind": 1,
            "amount": 300,
            "bucket": 1,
            "source": "pettycash",
        }
    ]
    assert (after["moneyOut"] - before["moneyOut"], after["repairs"] - before["repairs"]) == (
        300,
        300,
    )


# --- reads ---------------------------------------------------------------------------------


async def test_the_overview_answers_in_wire_order_for_a_day_a_week_and_a_period(
    yard: Yard,
) -> None:
    await cash(yard, 1000, date="2026-10-05")
    ok(await post(yard, yard.clerk, "/entries", expense(yard, 300)))
    response, count = await statements(get(yard, yard.clerk, "/overview?period=week"))
    seen = ok(response)
    assert count == 2
    assert list(seen) == OVERVIEW_KEYS
    assert (seen["date"], seen["period"], seen["from"], seen["to"]) == (
        TODAY,
        "week",
        "2026-10-05",
        "2026-10-11",
    )
    assert list(seen["permissions"]) == PERMISSION_KEYS
    assert seen["permissions"]["holderId"] == str(yard.clerk.user_id)
    assert seen["holders"] == [
        {"id": str(yard.clerk.user_id), "name": "Wanjiru Kamau", "active": True}
    ]
    assert list(seen["figures"]) == FIGURE_KEYS
    assert (seen["figures"]["cashReceived"], seen["figures"]["waiting"]) == (1000, 300)
    assert [list(f) for f in seen["floats"]] == [FLOAT_KEYS]
    assert seen["floats"][0]["lastCashOn"] == "2026-10-05"
    span = ok(await get(yard, yard.reviewer, "/overview?from=2026-10-06&to=2026-10-07"))
    assert (span["period"], span["date"], span["figures"]["openingBalance"]) == (
        "range",
        TODAY,
        1000,
    )
    assert span["permissions"]["approvalLimit"] == 5000
    problem(
        await get(yard, yard.clerk, "/overview?period=month"),
        400,
        INVALID,
        "Choose a day or a week.",
    )
    problem(
        await get(yard, yard.clerk, f"/overview?holderId={yard.reviewer.user_id}"), 404, NOT_FOUND
    )


async def test_the_entry_filters_are_comma_lists_trimmed_and_deduplicated(yard: Yard) -> None:
    await cash(yard, 1000)
    made = ok(await post(yard, yard.clerk, "/entries", expense(yard, 300)))
    ok(
        await post(
            yard, yard.reviewer, f"/entries/{made['id']}/send-back", {"version": 1, "comment": "?"}
        )
    )
    response, count = await statements(
        get(yard, yard.reviewer, "/entries?kind=%20expense,,expense")
    )
    page = ok(response)
    assert count == 2
    assert list(page) == ["items", "pageNumber", "pageSize", "total"]
    assert (page["pageNumber"], page["pageSize"], page["total"]) == (1, 100, 1)
    assert [list(e) for e in page["items"]] == [ENTRY_KEYS]
    both = ok(
        await get(yard, yard.reviewer, "/entries?kind=cash,expense&status=sentBack,%20waiting")
    )
    assert [e["status"] for e in both["items"]] == ["sentBack"]
    everything = ok(await get(yard, yard.reviewer, "/entries?kind=,&status="))
    assert everything["total"] == 2
    found = ok(await get(yard, yard.reviewer, "/entries?q=TYRE"))
    assert [e["id"] for e in found["items"]] == [made["id"]]
    problem(
        await get(yard, yard.reviewer, "/entries?kind=bogus"),
        400,
        INVALID,
        "Choose an expense, a credit note or cash.",
    )
    problem(
        await get(yard, yard.reviewer, "/entries?status=Waiting"),
        400,
        INVALID,
        sentence("pettycash_status_invalid"),
    )
    problem(await get(yard, yard.reviewer, f"/entries?holderId={uuid4()}"), 404, NOT_FOUND)
    problem(
        await get(yard, yard.reviewer, "/entries?pageSize=101"),
        400,
        INVALID,
        sentence("page_out_of_range"),
    )


async def test_the_options_and_dashboard_follow_the_rights(yard: Yard) -> None:
    ok(await post(yard, yard.clerk, "/entries", expense(yard, 6000)))
    response, count = await statements(get(yard, yard.clerk, "/options"))
    options = ok(response)
    assert count == 2
    assert list(options) == ["vehicles", "items", "holders"]
    assert options["vehicles"] == [
        {
            "id": yard.vehicle,
            "companyId": options["vehicles"][0]["companyId"],
            "companyName": "Petty Fleet",
            "registration": "KAA 501A",
            "active": True,
        }
    ]
    assert [list(i) for i in options["items"]] == [
        ["id", "name", "categoryId", "categoryName", "bucket"]
    ]
    assert options["holders"] == []
    issuing = ok(await get(yard, yard.reviewer, "/options?date=2026-10-01"))
    assert (issuing["vehicles"], issuing["items"]) == ([], [])
    assert [h["name"] for h in issuing["holders"]] == ["Antony Maina", "Wanjiru Kamau"]
    response, count = await statements(get(yard, yard.clerk, "/dashboard"))
    dashboard = ok(response)
    assert count == 2
    assert list(dashboard) == ["float", "approvals"]
    assert dashboard["float"] == {
        "balance": -6000,
        "waitingCount": 1,
        "waitingTotal": 6000,
        "sentBackCount": 0,
        "approvedThisMonth": 0,
    }
    assert dashboard["approvals"] is None
    approvals = ok(await get(yard, yard.reviewer, "/dashboard"))
    assert approvals["float"] is None
    assert approvals["approvals"] == {
        "count": 1,
        "total": 6000,
        "approvalLimit": 5000,
        "aboveLimit": 1,
        "holders": [
            {
                "holderId": str(yard.clerk.user_id),
                "name": "Wanjiru Kamau",
                "count": 1,
                "total": 6000,
                "oldest": TODAY,
            }
        ],
    }


# --- the edges of the routes ----------------------------------------------------------------


async def test_the_routes_refuse_a_bad_id_a_missing_content_type_and_no_bearer(
    yard: Yard,
) -> None:
    empty(await post(yard, yard.reviewer, "/entries/not-a-uuid/approve", {"version": 1}), 404)
    empty(
        await yard.api.client.post(
            "/setup/pettycash/entries", content=b"{}", headers=yard.clerk.headers
        ),
        415,
    )
    response = await yard.api.client.get("/setup/pettycash/overview")
    assert response.status_code == 401
    empty(await get(yard, yard.reviewer, "/nothing"), 404)
    nobody = await _person(yard.api, yard.org, "Revenue clerk", "0744000111", "Rita Clerk")
    problem(await get(yard, nobody, "/overview"), 403, FORBIDDEN)
    problem(await post(yard, nobody, "/entries", expense(yard)), 403, FORBIDDEN)


async def test_integers_beyond_their_column_types_are_refused_before_the_routine(
    yard: Yard,
) -> None:
    made = ok(await post(yard, yard.clerk, "/entries", expense(yard)))
    for path, payload, field in (
        (f"/entries/{made['id']}/approve", {"version": 2**63}, "version"),
        ("/approve", {"entries": [{"id": made["id"], "version": 2**63}]}, "entries.0.version"),
    ):
        response = await post(yard, yard.reviewer, path, payload)
        body = problem(response, 400, INVALID, response.json().get("detail"))
        assert list(body["errors"]) == [field]
    response = await get(yard, yard.reviewer, "/entries?page=2147483648")
    body = problem(response, 400, INVALID, response.json().get("detail"))
    assert list(body["errors"]) == ["query.page"]
    problem(
        await post(yard, yard.reviewer, f"/entries/{made['id']}/approve", {"version": 2**63 - 1}),
        409,
        CHANGED,
        "This entry was changed after you opened it. Check it and save again.",
    )


OPERATIONS = {
    ("GET", "/setup/pettycash/overview"): "GetPettyCashOverview",
    ("GET", "/setup/pettycash/entries"): "ListPettyCashEntries",
    ("GET", "/setup/pettycash/options"): "GetPettyCashOptions",
    ("GET", "/setup/pettycash/dashboard"): "GetPettyCashDashboard",
    ("POST", "/setup/pettycash/entries"): "CreatePettyCashEntry",
    ("PUT", "/setup/pettycash/entries/{id:uuid}"): "UpdatePettyCashEntry",
    ("POST", "/setup/pettycash/entries/{id:uuid}/approve"): "ApprovePettyCashEntry",
    ("POST", "/setup/pettycash/entries/{id:uuid}/send-back"): "SendBackPettyCashEntry",
    ("POST", "/setup/pettycash/entries/{id:uuid}/remove"): "RemovePettyCashEntry",
    ("POST", "/setup/pettycash/approve-day"): "ApprovePettyCashDay",
    ("POST", "/setup/pettycash/approve"): "ApprovePettyCashEntries",
    ("POST", "/setup/pettycash/entries/{id:uuid}/reject"): "RejectPettyCashEntry",
    ("POST", "/setup/pettycash/entries/{id:uuid}/reopen"): "ReopenPettyCashEntry",
}


async def test_every_petty_cash_route_has_its_operation_id_and_the_petty_cash_tag() -> None:
    routes = {
        (method, getattr(route, "path", "")): getattr(route, "operation_id", None)
        for route in router.routes
        for method in getattr(route, "methods", ())
    }
    assert routes == OPERATIONS
    assert {tuple(getattr(route, "tags", ())) for route in router.routes} == {("Petty cash",)}


def sentence(code: str) -> str:
    detail = MESSAGES[code].detail
    assert detail is not None
    return detail
