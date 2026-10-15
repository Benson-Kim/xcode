"""The expense catalogue routes against the real database (``docs/06-http-contract.md`` section
2.6): categories with their nested items and main category in wire order, the item options,
create and update of a category under a main category or none (an absent ``mainCategoryId``
keeps it, ``null`` takes it away; a ``bucket`` is ignored), stop and restore (no body is read),
create and rename of an item, the main categories (S50 to S52), the refusals with their exact
sentences, the change-log entries each write leaves
with their JSON text snapshots, the body routes that require JSON (415), the 401, 403 and 404
answers, the paging refusals and the statement budget of 2."""

from __future__ import annotations

import json
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
from ..support.tenancy import set_override

pytestmark = pytest.mark.asyncio(loop_scope="session")

CATEGORY_KEYS = [
    "id",
    "name",
    "bucket",
    "active",
    "stoppedOn",
    "items",
    "mainCategoryId",
    "mainCategoryName",
]
ITEM_KEYS = ["id", "categoryId", "name", "active", "stoppedOn"]
OPTION_KEYS = [
    "id",
    "name",
    "categoryId",
    "categoryName",
    "bucket",
    "mainCategoryId",
    "mainCategoryName",
]
MAIN_KEYS = ["id", "name", "categoryCount", "itemCount"]
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
NAME_LENGTH = "Name must contain 1-100 characters."
ALREADY_OFF = "It is already turned off. Turn it on first to cancel that."
UNKNOWN = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


def organization(api: AuthApi) -> UUID:
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    return UUID(str(row["id"]))


async def category(api: AuthApi, member: Member, name: str, main: str | None = None) -> str:
    response = await api.client.post(
        "/setup/expense-categories",
        json={"name": name, "mainCategoryId": main},
        headers=member.headers,
    )
    body = ok(response)
    assert list(body) == ["id"]
    return str(body["id"])


async def main_category(api: AuthApi, member: Member, name: str) -> str:
    response = await api.client.post(
        "/setup/expense-main-categories", json={"name": name}, headers=member.headers
    )
    body = ok(response)
    assert list(body) == ["id"]
    return str(body["id"])


async def item(api: AuthApi, member: Member, category_id: str, name: str) -> str:
    response = await api.client.post(
        f"/setup/expense-categories/{category_id}/items",
        json={"name": name},
        headers=member.headers,
    )
    body = ok(response)
    assert list(body) == ["id"]
    return str(body["id"])


async def entries(api: AuthApi, member: Member) -> list[dict[str, Any]]:
    """The expense change log, newest first."""
    page = ok(
        await api.client.get("/setup/history?section=expenses&pageSize=100", headers=member.headers)
    )
    items: list[dict[str, Any]] = page["items"]
    return items


async def reasons(api: AuthApi, member: Member) -> list[str]:
    return [entry["reason"] for entry in reversed(await entries(api, member))]


def stopped(api: AuthApi, table: str, record: str, day: date | None) -> None:
    api.owner.execute(
        f"UPDATE setup.{table} SET stopped_on = %s WHERE id = %s", (day, UUID(record))
    )


async def test_categories_list_by_name_with_their_items_by_name(
    api: AuthApi, owner: Member
) -> None:
    repairs = await main_category(api, owner, "Repairs")
    charges = await category(api, owner, "Charges")
    loans = await category(api, owner, "Loans")
    garage = await category(api, owner, "Garage and repairs", repairs)
    await item(api, owner, charges, "Parking")
    tyres = await item(api, owner, garage, "Tyres")
    towing = await item(api, owner, garage, "Towing")
    ok(await api.client.post(f"/setup/expense-items/{tyres}/stop", headers=owner.headers))
    stopped(api, "expense_categories", loans, date(2026, 10, 8))
    response, count = await statements(
        api.client.get("/setup/expense-categories", headers=owner.headers)
    )
    page = ok(response)
    assert count == 2
    assert list(page) == ["items", "pageNumber", "pageSize", "total"]
    assert (page["pageNumber"], page["pageSize"], page["total"]) == (1, 25, 3)
    assert [c["name"] for c in page["items"]] == ["Charges", "Garage and repairs", "Loans"]
    assert [list(c) for c in page["items"]] == [CATEGORY_KEYS] * 3
    garage_row = page["items"][1]
    assert garage_row == {
        "id": garage,
        "name": "Garage and repairs",
        "bucket": None,
        "active": True,
        "stoppedOn": None,
        "mainCategoryId": repairs,
        "mainCategoryName": "Repairs",
        "items": [
            {
                "id": towing,
                "categoryId": garage,
                "name": "Towing",
                "active": True,
                "stoppedOn": None,
            },
            {
                "id": tyres,
                "categoryId": garage,
                "name": "Tyres",
                "active": False,
                "stoppedOn": "2026-10-07",
            },
        ],
    }
    assert [list(i) for i in garage_row["items"]] == [ITEM_KEYS, ITEM_KEYS]
    loans_row = page["items"][2]
    assert (loans_row["mainCategoryId"], loans_row["mainCategoryName"]) == (None, None)
    assert (loans_row["active"], loans_row["stoppedOn"], loans_row["items"]) == (
        True,
        "2026-10-08",
        [],
    )


async def test_categories_page_by_name(api: AuthApi, owner: Member) -> None:
    for name in ("Charlie", "Alpha", "Bravo"):
        await category(api, owner, name)
    page = ok(
        await api.client.get("/setup/expense-categories?page=2&pageSize=1", headers=owner.headers)
    )
    assert (page["pageNumber"], page["pageSize"], page["total"]) == (2, 1, 3)
    assert [c["name"] for c in page["items"]] == ["Bravo"]


async def test_the_category_list_refuses_a_page_out_of_range(api: AuthApi, owner: Member) -> None:
    for query in ("page=0", "pageSize=101", "page=100001", "pageSize=0"):
        problem(
            await api.client.get(f"/setup/expense-categories?{query}", headers=owner.headers),
            400,
            INVALID,
            PAGING,
        )
    response = await api.client.get("/setup/expense-categories?page=one", headers=owner.headers)
    assert response.status_code == 400


async def test_the_options_leave_out_stopped_items_and_items_of_stopped_categories(
    api: AuthApi, owner: Member
) -> None:
    repairs = await main_category(api, owner, "Repairs")
    charges = await category(api, owner, "Charges")
    loans = await category(api, owner, "Loans")
    garage = await category(api, owner, "Garage and repairs", repairs)
    parking = await item(api, owner, charges, "Parking")
    insurance = await item(api, owner, charges, "Insurance")
    await item(api, owner, loans, "Loan repayment")
    tyres = await item(api, owner, garage, "Tyres")
    towing = await item(api, owner, garage, "Towing")
    stopped(api, "expense_items", tyres, date(2026, 10, 7))
    stopped(api, "expense_items", towing, date(2026, 10, 8))
    stopped(api, "expense_categories", loans, date(2026, 10, 1))
    response, count = await statements(
        api.client.get("/setup/expense-items/options", headers=owner.headers)
    )
    options = ok(response)
    assert count == 2
    assert [list(option) for option in options] == [OPTION_KEYS] * 3
    assert options == [
        {
            "id": insurance,
            "name": "Insurance",
            "categoryId": charges,
            "categoryName": "Charges",
            "bucket": None,
            "mainCategoryId": None,
            "mainCategoryName": None,
        },
        {
            "id": parking,
            "name": "Parking",
            "categoryId": charges,
            "categoryName": "Charges",
            "bucket": None,
            "mainCategoryId": None,
            "mainCategoryName": None,
        },
        {
            "id": towing,
            "name": "Towing",
            "categoryId": garage,
            "categoryName": "Garage and repairs",
            "bucket": None,
            "mainCategoryId": repairs,
            "mainCategoryName": "Repairs",
        },
    ]


async def test_reading_needs_expense_or_schedule_access(api: AuthApi, owner: Member) -> None:
    await category(api, owner, "Charges")
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    problem(
        await api.client.get("/setup/expense-categories", headers=clerk.headers), 403, FORBIDDEN
    )
    problem(
        await api.client.get("/setup/expense-items/options", headers=clerk.headers), 403, FORBIDDEN
    )
    manager = await join(api, email="sam@example.com", phone="0733000111", role="Fleet manager")
    page = ok(await api.client.get("/setup/expense-categories", headers=manager.headers))
    assert page["total"] == 1
    assert ok(await api.client.get("/setup/expense-items/options", headers=manager.headers)) == []
    set_override(
        api.owner, Person(clerk.user_id, organization(api), "", "", "", "", ""), "scheduled.add"
    )
    for path in ("/setup/expense-items/options", "/setup/expense-categories"):
        assert (await api.client.get(path, headers=clerk.headers)).status_code == 200


async def test_every_write_needs_a_catalogue_right(api: AuthApi, owner: Member) -> None:
    charges = await category(api, owner, "Charges")
    parking = await item(api, owner, charges, "Parking")
    repairs = await main_category(api, owner, "Repairs")
    manager = await join(api, email="sam@example.com", phone="0733000111", role="Fleet manager")
    body = {"name": "Other"}
    calls = [
        api.client.post("/setup/expense-main-categories", json=body, headers=manager.headers),
        api.client.put(
            f"/setup/expense-main-categories/{repairs}", json=body, headers=manager.headers
        ),
        api.client.post("/setup/expense-categories", json=body, headers=manager.headers),
        api.client.put(f"/setup/expense-categories/{charges}", json=body, headers=manager.headers),
        api.client.post(f"/setup/expense-categories/{charges}/stop", headers=manager.headers),
        api.client.post(f"/setup/expense-categories/{charges}/restore", headers=manager.headers),
        api.client.post(
            f"/setup/expense-categories/{charges}/items", json=body, headers=manager.headers
        ),
        api.client.put(f"/setup/expense-items/{parking}", json=body, headers=manager.headers),
        api.client.post(f"/setup/expense-items/{parking}/stop", headers=manager.headers),
        api.client.post(f"/setup/expense-items/{parking}/restore", headers=manager.headers),
    ]
    for call in calls:
        problem(await call, 403, FORBIDDEN)
    assert await reasons(api, owner) == [
        "Added expense category Charges",
        "Added expense item Parking under Charges",
        "Added main category Repairs",
    ]


async def test_a_category_is_created_trimmed_and_logged(api: AuthApi, owner: Member) -> None:
    response, count = await statements(
        api.client.post(
            "/setup/expense-categories",
            json={"name": " Road costs ", "bucket": 2, "reason": "Not read"},
            headers=owner.headers,
        )
    )
    created = ok(response)
    assert count == 2
    assert list(created) == ["id"]
    (entry,) = await entries(api, owner)
    assert list(entry) == ENTRY_KEYS
    assert (entry["section"], entry["entityId"]) == ("expenses", created["id"])
    assert entry["reason"] == "Added expense category Road costs"
    assert entry["actorName"] == "Jane Doe"
    assert entry["before"] == "null"
    assert entry["after"] == (
        f'{{"Id":"{created["id"]}","Name":"Road costs","MainCategoryId":null,"StoppedOn":null}}'
    )
    page = ok(await api.client.get("/setup/expense-categories", headers=owner.headers))
    assert [(c["name"], c["bucket"]) for c in page["items"]] == [("Road costs", None)]


@pytest.mark.parametrize("body", [{"mainCategoryId": None}, {"name": None}])
async def test_a_category_without_a_name_is_refused(
    api: AuthApi, owner: Member, body: dict[str, Any]
) -> None:
    problem(
        await api.client.post("/setup/expense-categories", json=body, headers=owner.headers),
        400,
        INVALID,
        NAME_LENGTH,
    )


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
async def test_a_category_name_must_be_1_to_100_characters(
    api: AuthApi, owner: Member, name: str
) -> None:
    problem(
        await api.client.post(
            "/setup/expense-categories", json={"name": name}, headers=owner.headers
        ),
        400,
        INVALID,
        NAME_LENGTH,
    )


async def test_a_bucket_in_the_body_is_ignored(api: AuthApi, owner: Member) -> None:
    for number, bucket in enumerate((0, 4, -1, "two", 2.5, 3000000000)):
        ok(
            await api.client.post(
                "/setup/expense-categories",
                json={"name": f"Road costs {number}", "bucket": bucket},
                headers=owner.headers,
            )
        )
    page = ok(await api.client.get("/setup/expense-categories", headers=owner.headers))
    assert {c["bucket"] for c in page["items"]} == {None}


async def test_a_category_needs_a_known_main_category(api: AuthApi, owner: Member) -> None:
    problem(
        await api.client.post(
            "/setup/expense-categories",
            json={"name": "Road costs", "mainCategoryId": UNKNOWN},
            headers=owner.headers,
        ),
        404,
        NOT_FOUND,
    )
    malformed = await api.client.post(
        "/setup/expense-categories",
        json={"name": "Road costs", "mainCategoryId": "repairs"},
        headers=owner.headers,
    )
    assert malformed.status_code == 400
    assert await entries(api, owner) == []


async def test_a_category_name_is_unique_ignoring_case(api: AuthApi, owner: Member) -> None:
    await category(api, owner, "Charges")
    problem(
        await api.client.post(
            "/setup/expense-categories",
            json={"name": "CHARGES"},
            headers=owner.headers,
        ),
        400,
        INVALID,
        "That category already exists.",
    )


async def test_an_absent_main_category_is_kept_and_null_takes_it_away(
    api: AuthApi, owner: Member
) -> None:
    repairs = await main_category(api, owner, "Repairs")
    loans = await category(api, owner, "Loans")
    path = f"/setup/expense-categories/{loans}"
    for body in (
        {"name": "Bank loans"},
        {"name": "Bank loans", "mainCategoryId": repairs},
        {"name": "Bank loans", "bucket": 3},
        {"name": "Loans", "mainCategoryId": None},
    ):
        response, count = await statements(api.client.put(path, json=body, headers=owner.headers))
        assert ok(response) == {"id": loans}
        assert count == 2
    assert (await reasons(api, owner))[2:] == [
        "Renamed expense category Loans to Bank loans",
        "Moved expense category Bank loans to main category Repairs",
        "Renamed expense category Bank loans to Loans, moved to no main category",
    ]
    last = (await entries(api, owner))[0]
    assert (last["section"], last["entityId"]) == ("expenses", loans)
    assert json.loads(last["before"]) == {
        "Id": loans,
        "Name": "Bank loans",
        "MainCategoryId": repairs,
        "StoppedOn": None,
    }
    assert last["after"] == (
        f'{{"Id":"{loans}","Name":"Loans","MainCategoryId":null,"StoppedOn":null}}'
    )


async def test_a_category_saved_as_it_is_is_ok_and_leaves_no_history(
    api: AuthApi, owner: Member
) -> None:
    loans = await category(api, owner, "Loans")
    before = await entries(api, owner)
    for body in ({"name": " Loans ", "bucket": 3}, {"name": "Loans", "mainCategoryId": None}):
        response, count = await statements(
            api.client.put(f"/setup/expense-categories/{loans}", json=body, headers=owner.headers)
        )
        assert ok(response) == {"id": loans}
        assert count == 2
    assert await entries(api, owner) == before


async def test_a_category_update_checks_name_then_record_then_main_category_then_uniqueness(
    api: AuthApi, owner: Member
) -> None:
    await category(api, owner, "Charges")
    loans = await category(api, owner, "Loans")
    for path, body, status, detail in [
        (UNKNOWN, {"name": "", "mainCategoryId": UNKNOWN}, 400, NAME_LENGTH),
        (UNKNOWN, {"name": "Fresh", "mainCategoryId": UNKNOWN}, 404, None),
        (loans, {"name": "charges", "mainCategoryId": UNKNOWN}, 404, None),
        (loans, {"name": "charges"}, 400, "That category already exists."),
    ]:
        response = await api.client.put(
            f"/setup/expense-categories/{path}", json=body, headers=owner.headers
        )
        if status == 404:
            problem(response, 404, NOT_FOUND)
        else:
            problem(response, status, INVALID, detail)


async def test_turning_a_category_off_and_on_reads_no_body(api: AuthApi, owner: Member) -> None:
    loans = await category(api, owner, "Loans")
    path = f"/setup/expense-categories/{loans}"
    response, count = await statements(api.client.post(f"{path}/stop", headers=owner.headers))
    assert ok(response) == {"id": loans}
    assert count == 2
    stop = (await entries(api, owner))[0]
    assert stop["reason"] == "Turned off expense category Loans"
    assert json.loads(stop["after"])["StoppedOn"] == "2026-10-07"
    page = ok(await api.client.get("/setup/expense-categories", headers=owner.headers))
    assert (page["items"][0]["active"], page["items"][0]["stoppedOn"]) == (False, "2026-10-07")
    again = await api.client.post(f"{path}/stop", headers=owner.headers)
    assert ok(again) == {"id": loans}
    assert len(await entries(api, owner)) == 2
    response, count = await statements(
        api.client.post(f"{path}/restore", content=b"ignored", headers=owner.headers)
    )
    assert ok(response) == {"id": loans}
    assert count == 2
    restored = (await entries(api, owner))[0]
    assert restored["reason"] == "Turned on expense category Loans"
    assert json.loads(restored["after"])["StoppedOn"] is None
    ok(await api.client.post(f"{path}/restore", headers=owner.headers))
    assert len(await entries(api, owner)) == 3


@pytest.mark.parametrize("day", [date(2026, 10, 2), date(2026, 10, 9)])
async def test_a_category_stopped_on_another_date_must_be_turned_on_first(
    api: AuthApi, owner: Member, day: date
) -> None:
    loans = await category(api, owner, "Loans")
    stopped(api, "expense_categories", loans, day)
    path = f"/setup/expense-categories/{loans}"
    problem(await api.client.post(f"{path}/stop", headers=owner.headers), 400, INVALID, ALREADY_OFF)
    assert ok(await api.client.post(f"{path}/restore", headers=owner.headers)) == {"id": loans}
    page = ok(await api.client.get("/setup/expense-categories", headers=owner.headers))
    assert page["items"][0]["stoppedOn"] is None


async def test_an_item_is_added_under_its_category(api: AuthApi, owner: Member) -> None:
    charges = await category(api, owner, "Charges")
    response, count = await statements(
        api.client.post(
            f"/setup/expense-categories/{charges}/items",
            json={"name": " Tolls ", "reason": "Not read"},
            headers=owner.headers,
        )
    )
    created = ok(response)
    assert count == 2
    assert list(created) == ["id"]
    entry = (await entries(api, owner))[0]
    assert (entry["section"], entry["entityId"]) == ("expenses", created["id"])
    assert entry["reason"] == "Added expense item Tolls under Charges"
    assert entry["before"] == "null"
    assert entry["after"] == (
        f'{{"Id":"{created["id"]}","CategoryId":"{charges}","Name":"Tolls","StoppedOn":null}}'
    )
    page = ok(await api.client.get("/setup/expense-categories", headers=owner.headers))
    assert [i["name"] for i in page["items"][0]["items"]] == ["Tolls"]


async def test_an_item_name_is_unique_within_its_category_ignoring_case(
    api: AuthApi, owner: Member
) -> None:
    charges = await category(api, owner, "Charges")
    garage = await category(api, owner, "Garage and repairs")
    await item(api, owner, charges, "Parking")
    problem(
        await api.client.post(
            f"/setup/expense-categories/{charges}/items",
            json={"name": "parking"},
            headers=owner.headers,
        ),
        400,
        INVALID,
        "That item already exists in this category.",
    )
    await item(api, owner, garage, "Parking")


async def test_a_stopped_category_still_accepts_items(api: AuthApi, owner: Member) -> None:
    loans = await category(api, owner, "Loans")
    stopped(api, "expense_categories", loans, date(2026, 10, 1))
    await item(api, owner, loans, "Interest")


async def test_an_item_needs_a_known_category_and_a_name(api: AuthApi, owner: Member) -> None:
    charges = await category(api, owner, "Charges")
    problem(
        await api.client.post(
            f"/setup/expense-categories/{UNKNOWN}/items", json={"name": ""}, headers=owner.headers
        ),
        404,
        NOT_FOUND,
    )
    for name in ("", "  ", "x" * 101, None):
        problem(
            await api.client.post(
                f"/setup/expense-categories/{charges}/items",
                json={"name": name},
                headers=owner.headers,
            ),
            400,
            INVALID,
            NAME_LENGTH,
        )


async def test_renaming_an_item(api: AuthApi, owner: Member) -> None:
    garage = await category(api, owner, "Garage and repairs")
    towing = await item(api, owner, garage, "Towing")
    await item(api, owner, garage, "Tyres")
    path = f"/setup/expense-items/{towing}"
    response, count = await statements(
        api.client.put(path, json={"name": "Road towing"}, headers=owner.headers)
    )
    assert ok(response) == {"id": towing}
    assert count == 2
    entry = (await entries(api, owner))[0]
    assert entry["reason"] == "Renamed expense item Towing to Road towing"
    assert entry["entityId"] == towing
    assert json.loads(entry["before"])["Name"] == "Towing"
    assert json.loads(entry["after"])["Name"] == "Road towing"
    before = await entries(api, owner)
    assert ok(await api.client.put(path, json={"name": "Road towing"}, headers=owner.headers)) == {
        "id": towing
    }
    assert await entries(api, owner) == before
    problem(
        await api.client.put(path, json={"name": "TYRES"}, headers=owner.headers),
        400,
        INVALID,
        "That item already exists in this category.",
    )
    problem(
        await api.client.put(path, json={"name": " "}, headers=owner.headers),
        400,
        INVALID,
        NAME_LENGTH,
    )
    problem(
        await api.client.put(
            f"/setup/expense-items/{UNKNOWN}", json={"name": "Tyres"}, headers=owner.headers
        ),
        404,
        NOT_FOUND,
    )
    problem(
        await api.client.put(
            f"/setup/expense-items/{UNKNOWN}", json={"name": " "}, headers=owner.headers
        ),
        400,
        INVALID,
        NAME_LENGTH,
    )


async def test_turning_an_item_off_and_on_reads_no_body(api: AuthApi, owner: Member) -> None:
    garage = await category(api, owner, "Garage and repairs")
    tyres = await item(api, owner, garage, "Tyres")
    path = f"/setup/expense-items/{tyres}"
    response, count = await statements(api.client.post(f"{path}/stop", headers=owner.headers))
    assert ok(response) == {"id": tyres}
    assert count == 2
    assert ok(await api.client.post(f"{path}/stop", headers=owner.headers)) == {"id": tyres}
    page = ok(await api.client.get("/setup/expense-categories", headers=owner.headers))
    assert page["items"][0]["items"][0]["stoppedOn"] == "2026-10-07"
    response, count = await statements(api.client.post(f"{path}/restore", headers=owner.headers))
    assert ok(response) == {"id": tyres}
    assert count == 2
    assert (await reasons(api, owner))[2:] == [
        "Turned off expense item Tyres",
        "Turned on expense item Tyres",
    ]
    stopped(api, "expense_items", tyres, date(2026, 10, 9))
    problem(await api.client.post(f"{path}/stop", headers=owner.headers), 400, INVALID, ALREADY_OFF)


async def test_a_body_route_without_json_is_415(api: AuthApi, owner: Member) -> None:
    charges = await category(api, owner, "Charges")
    parking = await item(api, owner, charges, "Parking")
    payload = json.dumps({"name": "Other"}).encode()
    text = {**owner.headers, "Content-Type": "text/plain"}
    for method, path in [
        ("POST", "/setup/expense-categories"),
        ("PUT", f"/setup/expense-categories/{charges}"),
        ("POST", f"/setup/expense-categories/{charges}/items"),
        ("PUT", f"/setup/expense-items/{parking}"),
    ]:
        empty(await api.client.request(method, path, content=payload, headers=text), 415)
        empty(await api.client.request(method, path, content=payload, headers=owner.headers), 415)
    malformed = await api.client.post(
        "/setup/expense-categories",
        content=b"{not json",
        headers={**owner.headers, "Content-Type": "application/json"},
    )
    assert malformed.status_code == 400
    assert len(await entries(api, owner)) == 2


async def test_an_unknown_or_malformed_id_is_not_found(api: AuthApi, owner: Member) -> None:
    for path in (
        f"/setup/expense-categories/{UNKNOWN}/stop",
        f"/setup/expense-categories/{UNKNOWN}/restore",
        f"/setup/expense-items/{UNKNOWN}/stop",
        f"/setup/expense-items/{UNKNOWN}/restore",
    ):
        problem(await api.client.post(path, headers=owner.headers), 404, NOT_FOUND)
    for path in (
        "/setup/expense-categories/not-a-uuid/stop",
        "/setup/expense-categories/not-a-uuid/restore",
        "/setup/expense-categories/not-a-uuid/items",
        "/setup/expense-items/not-a-uuid/stop",
        "/setup/expense-items/not-a-uuid/restore",
    ):
        empty(await api.client.post(path, json={"name": "X"}, headers=owner.headers), 404)
    for path in ("/setup/expense-categories/not-a-uuid", "/setup/expense-items/not-a-uuid"):
        empty(await api.client.put(path, json={"name": "X"}, headers=owner.headers), 404)


async def test_expense_routes_need_a_token(api: AuthApi, owner: Member) -> None:
    charges = await category(api, owner, "Charges")
    parking = await item(api, owner, charges, "Parking")
    empty(await api.client.get("/setup/expense-categories"), 401)
    empty(await api.client.get("/setup/expense-items/options"), 401)
    empty(await api.client.post("/setup/expense-categories", json={"name": "X"}), 401)
    empty(
        await api.client.put(f"/setup/expense-categories/{charges}", json={"name": "X"}),
        401,
    )
    for path in (
        f"/setup/expense-categories/{charges}/stop",
        f"/setup/expense-categories/{charges}/restore",
        f"/setup/expense-items/{parking}/stop",
        f"/setup/expense-items/{parking}/restore",
    ):
        empty(await api.client.post(path), 401)
    empty(
        await api.client.post(f"/setup/expense-categories/{charges}/items", json={"name": "X"}), 401
    )
    empty(await api.client.put(f"/setup/expense-items/{parking}", json={"name": "X"}), 401)


# --- main categories (S50 to S52) -----------------------------------------------------


async def test_main_categories_list_by_name_with_their_counts(api: AuthApi, owner: Member) -> None:
    repairs = await main_category(api, owner, "Repairs")
    finance = await main_category(api, owner, "Finance")
    garage = await category(api, owner, "Garage", repairs)
    await item(api, owner, garage, "Service")
    await item(api, owner, garage, "Towing")
    await category(api, owner, "Fuel")
    response, count = await statements(
        api.client.get("/setup/expense-main-categories", headers=owner.headers)
    )
    page = ok(response)
    assert count == 2
    assert list(page) == ["items", "pageNumber", "pageSize", "total", "categoriesWithoutMain"]
    assert [list(m) for m in page["items"]] == [MAIN_KEYS, MAIN_KEYS]
    assert page == {
        "items": [
            {"id": finance, "name": "Finance", "categoryCount": 0, "itemCount": 0},
            {"id": repairs, "name": "Repairs", "categoryCount": 1, "itemCount": 2},
        ],
        "pageNumber": 1,
        "pageSize": 25,
        "total": 2,
        "categoriesWithoutMain": 1,
    }
    second = ok(
        await api.client.get(
            "/setup/expense-main-categories?page=2&pageSize=1", headers=owner.headers
        )
    )
    assert [m["name"] for m in second["items"]] == ["Repairs"]
    problem(
        await api.client.get("/setup/expense-main-categories?page=0", headers=owner.headers),
        400,
        INVALID,
        PAGING,
    )


async def test_a_main_category_is_added_and_renamed_and_logged(api: AuthApi, owner: Member) -> None:
    response, count = await statements(
        api.client.post(
            "/setup/expense-main-categories", json={"name": " Repairs "}, headers=owner.headers
        )
    )
    repairs = str(ok(response)["id"])
    assert count == 2
    response, count = await statements(
        api.client.put(
            f"/setup/expense-main-categories/{repairs}",
            json={"name": "Garage costs"},
            headers=owner.headers,
        )
    )
    assert ok(response) == {"id": repairs}
    assert count == 2
    before = await entries(api, owner)
    ok(
        await api.client.put(
            f"/setup/expense-main-categories/{repairs}",
            json={"name": "Garage costs"},
            headers=owner.headers,
        )
    )
    assert await entries(api, owner) == before
    assert await reasons(api, owner) == [
        "Added main category Repairs",
        "Renamed main category Repairs to Garage costs",
    ]
    last = before[0]
    assert (last["section"], last["entityId"]) == ("expenses", repairs)
    assert last["after"] == f'{{"Id":"{repairs}","Name":"Garage costs"}}'


async def test_a_main_category_is_refused_with_its_sentence(api: AuthApi, owner: Member) -> None:
    repairs = await main_category(api, owner, "Repairs")
    finance = await main_category(api, owner, "Finance")
    for body, detail in [
        ({"name": "REPAIRS"}, "That main category already exists."),
        ({"name": " "}, NAME_LENGTH),
        ({}, NAME_LENGTH),
        ({"name": "x" * 101}, NAME_LENGTH),
    ]:
        problem(
            await api.client.post(
                "/setup/expense-main-categories", json=body, headers=owner.headers
            ),
            400,
            INVALID,
            detail,
        )
    problem(
        await api.client.put(
            f"/setup/expense-main-categories/{finance}",
            json={"name": "repairs"},
            headers=owner.headers,
        ),
        400,
        INVALID,
        "That main category already exists.",
    )
    problem(
        await api.client.put(
            f"/setup/expense-main-categories/{UNKNOWN}", json={"name": "X"}, headers=owner.headers
        ),
        404,
        NOT_FOUND,
    )
    empty(
        await api.client.put(
            "/setup/expense-main-categories/repairs", json={"name": "X"}, headers=owner.headers
        ),
        404,
    )
    assert len(await entries(api, owner)) == 2
    assert repairs != finance


async def test_main_categories_need_their_rights_and_a_token(api: AuthApi, owner: Member) -> None:
    repairs = await main_category(api, owner, "Repairs")
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    problem(
        await api.client.get("/setup/expense-main-categories", headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    manager = await join(api, email="sam@example.com", phone="0733000111", role="Fleet manager")
    assert (
        ok(await api.client.get("/setup/expense-main-categories", headers=manager.headers))["total"]
        == 1
    )
    empty(await api.client.get("/setup/expense-main-categories"), 401)
    empty(await api.client.post("/setup/expense-main-categories", json={"name": "X"}), 401)
    empty(
        await api.client.put(f"/setup/expense-main-categories/{repairs}", json={"name": "X"}),
        401,
    )
