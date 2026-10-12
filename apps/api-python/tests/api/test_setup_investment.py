"""The investment routes against the real database (``docs/06-http-contract.md`` section 2.7):
the investment document in wire order with its entries and the share paid off (null when
nothing is invested, rounded half away from zero, from the report scenario's net), add, update
and delete with their refusals and exact sentences, the change-log entries each write leaves
(kept against the vehicle, the delete's ``after`` the text ``null``), the scoped viewer and
manager who get 404, the body routes that require JSON (415), the 401, 403 and 404 answers and
the statement budget of 2."""

from __future__ import annotations

import json
import re
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
from ..support.setup_rows import ReportFleet, seed_report_fleet
from ..support.tenancy import Member as Person
from ..support.tenancy import set_organization, set_override, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

INVESTMENT_KEYS = ["vehicleId", "totalInvested", "returned", "percentPaidOff", "entries"]
ENTRY_KEYS = ["id", "date", "description", "amount", "recordedBy", "recordedAt"]
HISTORY_KEYS = [
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
INSTANT = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00"
MONEY = "Amount must be positive with at most two decimal places."
DATE_INVALID = "An investment date is required and cannot be after the business date."
DESCRIPTION = "Say what it was, in 1-160 characters."
UNKNOWN = "00000000-0000-4000-8000-000000000000"


@dataclass(frozen=True, slots=True)
class Yard:
    report: ReportFleet
    kdc: str
    south: str

    @property
    def kda(self) -> str:
        return str(self.report.kda)

    @property
    def kdb(self) -> str:
        return str(self.report.kdb)


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


@pytest.fixture
async def yard(api: AuthApi, owner: Member) -> Yard:
    org = organization(api)
    set_organization(api.owner, org, business_date=date(2026, 3, 31))
    report = seed_report_fleet(api.owner, org, owner.user_id)
    south = ok(
        await api.client.post(
            "/setup/companies", json={"name": "South Line"}, headers=owner.headers
        )
    )["id"]
    kdc = ok(
        await api.client.post(
            "/setup/vehicles",
            json={
                "companyId": south,
                "registration": "KDC 200B",
                "fleetNumber": "200B",
                "joinedOn": "2026-03-01",
                "dayTargets": [1000] * 7,
            },
            headers=owner.headers,
        )
    )["id"]
    return Yard(report, str(kdc), str(south))


def person(api: AuthApi, member: Member) -> Person:
    return Person(member.user_id, organization(api), "", "", "", "", "")


async def invest(
    api: AuthApi,
    member: Member,
    vehicle: str,
    description: str = "Purchase",
    amount: float = 15000,
    day: str = "2026-02-01",
) -> str:
    response = await api.client.post(
        f"/setup/vehicles/{vehicle}/investment",
        json={"date": day, "description": description, "amount": amount},
        headers=member.headers,
    )
    body = ok(response)
    assert list(body) == ["id"]
    return str(body["id"])


async def get(api: AuthApi, member: Member, vehicle: str) -> dict[str, Any]:
    body: dict[str, Any] = ok(
        await api.client.get(f"/setup/vehicles/{vehicle}/investment", headers=member.headers)
    )
    return body


async def entries(api: AuthApi, member: Member) -> list[dict[str, Any]]:
    """The investment change log, newest first."""
    page = ok(
        await api.client.get(
            "/setup/history?section=investment&pageSize=100", headers=member.headers
        )
    )
    items: list[dict[str, Any]] = page["items"]
    return items


async def reasons(api: AuthApi, member: Member) -> list[str]:
    return [entry["reason"] for entry in reversed(await entries(api, member))]


def snapshot(entry: str, vehicle: str, day: str, description: str, amount: str) -> str:
    return (
        f'{{"Id":"{entry}","VehicleId":"{vehicle}","Date":"{day}",'
        f'"Description":"{description}","Amount":{amount}}}'
    )


async def admin_of(api: AuthApi) -> Member:
    member = await join(api, email="olive@example.com", phone="0722000111", role="Office admin")
    set_scope(api.owner, member.user_id, organization(api), all_companies=True)
    return member


async def scoped(api: AuthApi, yard: Yard, *grants: str) -> Member:
    """A fleet manager with the given grants who reaches only the report scenario's company."""
    member = await join(api, email="sam@example.com", phone="0733000111", role="Fleet manager")
    for grant in grants:
        set_override(api.owner, person(api, member), grant)
    set_scope(api.owner, member.user_id, organization(api), companies=[yard.report.company])
    return member


# --- get -------------------------------------------------------------------------------


async def test_the_document_lists_entries_by_date_then_instant_with_the_share_paid_off(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    purchase = await invest(api, owner, yard.kda, "Purchase", 15000, "2026-02-01")
    api.clock.advance(5)
    deposit = await invest(api, owner, yard.kda, "Deposit", 3999.5, "2026-02-01")
    api.clock.advance(5)
    booking = await invest(api, owner, yard.kda, "Booking", 1000.5, "2026-01-15")
    await invest(api, owner, yard.kdb, "Other vehicle", 99)
    response, count = await statements(
        api.client.get(f"/setup/vehicles/{yard.kda}/investment", headers=owner.headers)
    )
    document = ok(response)
    assert count == 2
    assert list(document) == INVESTMENT_KEYS
    listed = document.pop("entries")
    assert document == {
        "vehicleId": yard.kda,
        "totalInvested": 20000,
        "returned": 8150,
        "percentPaidOff": 41,
    }
    assert type(document["percentPaidOff"]) is int
    assert [list(entry) for entry in listed] == [ENTRY_KEYS] * 3
    assert [
        (e["id"], e["date"], e["description"], e["amount"], e["recordedBy"]) for e in listed
    ] == [
        (booking, "2026-01-15", "Booking", 1000.5, "Jane Doe"),
        (purchase, "2026-02-01", "Purchase", 15000, "Jane Doe"),
        (deposit, "2026-02-01", "Deposit", 3999.5, "Jane Doe"),
    ]
    assert all(re.fullmatch(INSTANT, e["recordedAt"]) for e in listed)
    assert listed[1]["recordedAt"] < listed[2]["recordedAt"] < listed[0]["recordedAt"]


async def test_nothing_invested_has_no_percentage(api: AuthApi, owner: Member, yard: Yard) -> None:
    assert await get(api, owner, yard.kdc) == {
        "vehicleId": yard.kdc,
        "totalInvested": 0,
        "returned": 0,
        "percentPaidOff": None,
        "entries": [],
    }


@pytest.mark.parametrize(
    ("vehicle", "invested", "returned", "percent"),
    [
        ("kda", 16300, 8150, 50),
        ("kda", 20000, 8150, 41),
        ("kda", 13040, 8150, 63),
        ("kdb", 10000, -2500, -25),
        ("kdb", 4000, -2500, -63),
    ],
)
async def test_the_share_paid_off_rounds_half_away_from_zero(
    api: AuthApi,
    owner: Member,
    yard: Yard,
    vehicle: str,
    invested: int,
    returned: int,
    percent: int,
) -> None:
    target = yard.kda if vehicle == "kda" else yard.kdb
    await invest(api, owner, target, "Purchase", invested)
    document = await get(api, owner, target)
    assert (document["totalInvested"], document["returned"], document["percentPaidOff"]) == (
        invested,
        returned,
        percent,
    )


async def test_reading_needs_invest_view_and_a_vehicle_in_reach(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0744000111", role="Revenue clerk")
    problem(
        await api.client.get(f"/setup/vehicles/{yard.kda}/investment", headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.get(f"/setup/vehicles/{UNKNOWN}/investment", headers=owner.headers),
        404,
        NOT_FOUND,
    )
    viewer = await scoped(api, yard, "reports.investment")
    assert (await get(api, viewer, yard.kda))["returned"] == 8150
    problem(
        await api.client.get(f"/setup/vehicles/{yard.kdc}/investment", headers=viewer.headers),
        404,
        NOT_FOUND,
    )


async def test_a_vehicle_scope_reaches_only_those_vehicles(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    member = await join(api, email="vic@example.com", phone="0755000111", role="Fleet manager")
    set_override(api.owner, person(api, member), "reports.investment")
    set_scope(api.owner, member.user_id, organization(api), vehicles=[yard.report.kdb])
    assert (await get(api, member, yard.kdb))["vehicleId"] == yard.kdb
    problem(
        await api.client.get(f"/setup/vehicles/{yard.kda}/investment", headers=member.headers),
        404,
        NOT_FOUND,
    )


# --- add -------------------------------------------------------------------------------


async def test_an_added_entry_is_logged_against_the_vehicle(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    admin = await admin_of(api)
    response, count = await statements(
        api.client.post(
            f"/setup/vehicles/{yard.kda}/investment",
            json={"date": "2026-03-10", "description": "  New engine ", "amount": 12000.5},
            headers=admin.headers,
        )
    )
    created = ok(response)
    assert count == 2
    assert list(created) == ["id"]
    (entry,) = await entries(api, owner)
    assert list(entry) == HISTORY_KEYS
    assert (entry["section"], entry["entityId"]) == ("investment", yard.kda)
    assert entry["reason"] == "Recorded investment New engine on KDA 482M"
    assert entry["actorId"] == str(admin.user_id)
    assert entry["before"] == "null"
    assert entry["after"] == snapshot(
        created["id"], yard.kda, "2026-03-10", "New engine", "12000.5"
    )
    assert (await get(api, admin, yard.kda))["totalInvested"] == 12000.5


async def test_an_entry_dated_today_or_before_the_join_date_is_accepted(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    await invest(api, owner, yard.kda, "Deposit", 100, "2026-03-31")
    await invest(api, owner, yard.kda, "Deposit", 100, "2025-12-01")
    await invest(api, owner, yard.kda, "x" * 160, 1, "2026-03-31")
    assert len(await entries(api, owner)) == 3


@pytest.mark.parametrize(
    ("changes", "detail"),
    [
        ({"date": None}, DATE_INVALID),
        ({"date": "2026-04-01"}, DATE_INVALID),
        ({"description": None}, DESCRIPTION),
        ({"description": ""}, DESCRIPTION),
        ({"description": "   "}, DESCRIPTION),
        ({"description": "x" * 161}, DESCRIPTION),
        ({"amount": None}, MONEY),
        ({"amount": 0}, MONEY),
        ({"amount": -5}, MONEY),
        ({"amount": 1.005}, MONEY),
        ({"amount": 1000000000000}, MONEY),
    ],
)
async def test_a_malformed_entry_is_refused_with_its_sentence(
    api: AuthApi, owner: Member, yard: Yard, changes: dict[str, Any], detail: str
) -> None:
    body: dict[str, Any] = {"date": "2026-03-31", "description": "Deposit", "amount": 100}
    body.update(changes)
    problem(
        await api.client.post(
            f"/setup/vehicles/{yard.kda}/investment", json=body, headers=owner.headers
        ),
        400,
        INVALID,
        detail,
    )
    assert await entries(api, owner) == []


async def test_an_add_checks_the_vehicle_then_the_date_then_the_description_then_the_amount(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    problem(
        await api.client.post(
            f"/setup/vehicles/{UNKNOWN}/investment", json={}, headers=owner.headers
        ),
        404,
        NOT_FOUND,
    )
    path = f"/setup/vehicles/{yard.kda}/investment"
    for body, detail in [
        ({}, DATE_INVALID),
        ({"date": "2026-03-31"}, DESCRIPTION),
        ({"date": "2026-03-31", "description": "Deposit"}, MONEY),
    ]:
        problem(await api.client.post(path, json=body, headers=owner.headers), 400, INVALID, detail)


async def test_adding_needs_invest_manage(api: AuthApi, owner: Member, yard: Yard) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0744000111", role="Revenue clerk")
    viewer = await scoped(api, yard, "reports.investment")
    body = {"date": "2026-03-31", "description": "Deposit", "amount": 100}
    for member in (clerk, viewer):
        problem(
            await api.client.post(
                f"/setup/vehicles/{yard.kda}/investment", json=body, headers=member.headers
            ),
            403,
            FORBIDDEN,
        )
    assert await entries(api, owner) == []


# --- update ----------------------------------------------------------------------------


async def test_an_update_changes_the_entry_and_logs_both_sides(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    entry = await invest(api, owner, yard.kda)
    response, count = await statements(
        api.client.put(
            f"/setup/investment/{entry}",
            json={"date": "2026-02-03", "description": " Gearbox ", "amount": 9000},
            headers=owner.headers,
        )
    )
    assert ok(response) == {"id": entry}
    assert count == 2
    log = (await entries(api, owner))[0]
    assert (log["section"], log["entityId"]) == ("investment", yard.kda)
    assert log["reason"] == "Changed investment Gearbox on KDA 482M"
    assert log["before"] == snapshot(entry, yard.kda, "2026-02-01", "Purchase", "15000")
    assert log["after"] == snapshot(entry, yard.kda, "2026-02-03", "Gearbox", "9000")
    (listed,) = (await get(api, owner, yard.kda))["entries"]
    assert (listed["date"], listed["description"], listed["amount"]) == (
        "2026-02-03",
        "Gearbox",
        9000,
    )


async def test_an_update_that_changes_nothing_is_ok_and_leaves_no_history(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    entry = await invest(api, owner, yard.kda)
    before = await entries(api, owner)
    response, count = await statements(
        api.client.put(
            f"/setup/investment/{entry}",
            json={"date": "2026-02-01", "description": " Purchase  ", "amount": 15000.0},
            headers=owner.headers,
        )
    )
    assert ok(response) == {"id": entry}
    assert count == 2
    assert await entries(api, owner) == before


async def test_an_update_checks_the_entry_then_the_date_then_the_description_then_the_amount(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    entry = await invest(api, owner, yard.kda)
    problem(
        await api.client.put(f"/setup/investment/{UNKNOWN}", json={}, headers=owner.headers),
        404,
        NOT_FOUND,
    )
    path = f"/setup/investment/{entry}"
    for body, detail in [
        ({}, DATE_INVALID),
        ({"date": "2026-04-01"}, DATE_INVALID),
        ({"date": "2026-03-31", "description": "   "}, DESCRIPTION),
        ({"date": "2026-03-31", "description": "x" * 161, "amount": 1}, DESCRIPTION),
        ({"date": "2026-03-31", "description": "Deposit", "amount": 0.001}, MONEY),
    ]:
        problem(await api.client.put(path, json=body, headers=owner.headers), 400, INVALID, detail)


# --- delete ----------------------------------------------------------------------------


async def test_a_delete_removes_the_entry_and_the_log_keeps_what_it_held(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    entry = await invest(api, owner, yard.kda, "Purchase", 15000.25)
    kept = await invest(api, owner, yard.kda, "Deposit", 5000)
    admin = await admin_of(api)
    response, count = await statements(
        api.client.delete(f"/setup/investment/{entry}", headers=admin.headers)
    )
    assert ok(response) == {"id": entry}
    assert count == 2
    log = (await entries(api, owner))[0]
    assert (log["section"], log["entityId"]) == ("investment", yard.kda)
    assert log["reason"] == "Removed investment Purchase on KDA 482M"
    assert log["before"] == snapshot(entry, yard.kda, "2026-02-01", "Purchase", "15000.25")
    assert log["after"] == "null"
    document = await get(api, owner, yard.kda)
    assert [e["id"] for e in document["entries"]] == [kept]
    assert document["totalInvested"] == 5000
    problem(
        await api.client.delete(f"/setup/investment/{entry}", headers=admin.headers),
        404,
        NOT_FOUND,
    )


async def test_the_last_entry_removed_leaves_no_percentage(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    entry = await invest(api, owner, yard.kda)
    ok(await api.client.delete(f"/setup/investment/{entry}", headers=owner.headers))
    document = await get(api, owner, yard.kda)
    assert (document["totalInvested"], document["percentPaidOff"], document["entries"]) == (
        0,
        None,
        [],
    )
    assert await reasons(api, owner) == [
        "Recorded investment Purchase on KDA 482M",
        "Removed investment Purchase on KDA 482M",
    ]


# --- scope, permissions, bodies and tokens ---------------------------------------------


async def test_a_scoped_manager_cannot_reach_an_entry_outside_the_scope(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    outside = await invest(api, owner, yard.kdc, "Outside")
    inside = await invest(api, owner, yard.kda, "Inside")
    manager = await scoped(api, yard, "reports.investment", "vehicles.edit")
    body = {"date": "2026-03-31", "description": "Deposit", "amount": 100}
    problem(
        await api.client.post(
            f"/setup/vehicles/{yard.kdc}/investment", json=body, headers=manager.headers
        ),
        404,
        NOT_FOUND,
    )
    problem(
        await api.client.put(f"/setup/investment/{outside}", json=body, headers=manager.headers),
        404,
        NOT_FOUND,
    )
    problem(
        await api.client.delete(f"/setup/investment/{outside}", headers=manager.headers),
        404,
        NOT_FOUND,
    )
    assert ok(
        await api.client.put(f"/setup/investment/{inside}", json=body, headers=manager.headers)
    ) == {"id": inside}
    assert ok(await api.client.delete(f"/setup/investment/{inside}", headers=manager.headers)) == {
        "id": inside
    }
    assert [e["id"] for e in (await get(api, owner, yard.kdc))["entries"]] == [outside]


async def test_updating_and_deleting_need_invest_manage(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    entry = await invest(api, owner, yard.kda)
    clerk = await join(api, email="clerk@example.com", phone="0744000111", role="Revenue clerk")
    viewer = await scoped(api, yard, "reports.investment")
    body = {"date": "2026-03-31", "description": "Deposit", "amount": 100}
    for member in (clerk, viewer):
        problem(
            await api.client.put(f"/setup/investment/{entry}", json=body, headers=member.headers),
            403,
            FORBIDDEN,
        )
        problem(
            await api.client.delete(f"/setup/investment/{entry}", headers=member.headers),
            403,
            FORBIDDEN,
        )
    assert len((await get(api, owner, yard.kda))["entries"]) == 1


async def test_a_body_route_without_json_is_415(api: AuthApi, owner: Member, yard: Yard) -> None:
    entry = await invest(api, owner, yard.kda)
    payload = json.dumps({"date": "2026-03-31", "description": "Deposit", "amount": 100}).encode()
    text = {**owner.headers, "Content-Type": "text/plain"}
    for method, path in [
        ("POST", f"/setup/vehicles/{yard.kda}/investment"),
        ("PUT", f"/setup/investment/{entry}"),
    ]:
        empty(await api.client.request(method, path, content=payload, headers=text), 415)
        empty(await api.client.request(method, path, content=payload, headers=owner.headers), 415)
    malformed = await api.client.post(
        f"/setup/vehicles/{yard.kda}/investment",
        content=b"{not json",
        headers={**owner.headers, "Content-Type": "application/json"},
    )
    assert malformed.status_code == 400
    assert len(await entries(api, owner)) == 1


async def test_a_malformed_id_is_an_empty_not_found(api: AuthApi, owner: Member) -> None:
    body = {"date": "2026-03-31", "description": "Deposit", "amount": 100}
    empty(await api.client.get("/setup/vehicles/not-a-uuid/investment", headers=owner.headers), 404)
    empty(
        await api.client.post(
            "/setup/vehicles/not-a-uuid/investment", json=body, headers=owner.headers
        ),
        404,
    )
    empty(
        await api.client.put("/setup/investment/not-a-uuid", json=body, headers=owner.headers), 404
    )
    empty(await api.client.delete("/setup/investment/not-a-uuid", headers=owner.headers), 404)


async def test_investment_routes_need_a_token(api: AuthApi, owner: Member, yard: Yard) -> None:
    entry = await invest(api, owner, yard.kda)
    body = {"date": "2026-03-31", "description": "Deposit", "amount": 100}
    empty(await api.client.get(f"/setup/vehicles/{yard.kda}/investment"), 401)
    empty(await api.client.post(f"/setup/vehicles/{yard.kda}/investment", json=body), 401)
    empty(await api.client.put(f"/setup/investment/{entry}", json=body), 401)
    empty(await api.client.delete(f"/setup/investment/{entry}"), 401)
