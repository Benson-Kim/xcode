"""The vehicle routes against the real database (``docs/06-http-contract.md`` section 2.3): the
list in wire order for a manager and for an investment viewer, create with the registration
normalised, its fleet number and seven day targets, update with its fleet number and initial
investment (the targets left alone) and refusals, retire and restore with the days away, the
company options, the fleet number in the vehicle options, and the vehicle report (``period``,
``from`` and ``through``, its refusals and the figures of the report scenario); the change-log
entries each write leaves with their exact reasons, the lifecycle routes that require a JSON
body (415), the 401, 403 and 404 answers, the paging refusals and the statement budget of 2.
Target sets have their own module, ``test_setup_targets``."""

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
from ..support.setup_rows import ReportFleet, add_record, seed_report_fleet
from ..support.tenancy import Member as Person
from ..support.tenancy import set_organization, set_override, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

VEHICLE_KEYS = [
    "id",
    "companyId",
    "companyName",
    "registration",
    "joinedOn",
    "leftOn",
    "active",
    "weeklyTarget",
    "targets",
    "recurringItems",
    "away",
    "fleetNumber",
    "initialInvestment",
    "dayTargets",
    "nextTarget",
]
TARGET_KEYS = ["effectiveFrom", "weeklyAmount", "revision"]
AWAY_KEYS = ["leftOn", "returnedOn"]
REPORT_KEYS = [
    "vehicleId",
    "from",
    "through",
    "moneyIn",
    "target",
    "repairs",
    "charges",
    "loans",
    "moneyOut",
    "net",
    "savings",
    "afterSavings",
    "costs",
    "postings",
]
POSTING_KEYS = ["itemId", "versionId", "date", "name", "kind", "amount", "bucket", "source"]
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
MARCH_POSTINGS = [
    ("2026-03-01", "Crew lunch", 1, 50, 2),
    ("2026-03-01", "Tyres", 1, 100, 1),
    ("2026-03-02", "Crew lunch", 1, 50, 2),
    ("2026-03-02", "Parking", 1, 300, 2),
    ("2026-03-03", "Crew lunch", 1, 50, 2),
    ("2026-03-04", "Crew lunch", 1, 50, 2),
    ("2026-03-05", "Crew lunch", 1, 50, 2),
    ("2026-03-06", "Owner savings", 2, 1000, None),
    ("2026-03-08", "Tyres", 1, 100, 1),
    ("2026-03-09", "Parking", 1, 300, 2),
    ("2026-03-10", "Service", 1, 2000, 1),
    ("2026-03-13", "Owner savings", 2, 1000, None),
    ("2026-03-15", "Insurance", 1, 6000, 2),
    ("2026-03-15", "Tyres", 1, 100, 1),
    ("2026-03-16", "Parking", 1, 300, 2),
    ("2026-03-20", "Owner savings", 2, 1000, None),
    ("2026-03-22", "Tyres", 1, 100, 1),
    ("2026-03-25", "Service", 1, 2500, 1),
    ("2026-03-27", "Owner savings", 2, 1000, None),
    ("2026-03-29", "Tyres", 1, 100, 1),
    ("2026-03-31", "Loan repayment", 1, 10000, 3),
]
PAGING = "Page must be 1\u2013100000 and page size 1\u2013100."
REASON_LENGTH = "A reason of 1\u2013500 characters is required."
MONEY = "Amount must be positive with at most two decimal places."
UNSTORABLE = "Text cannot contain U+0000 or an unpaired surrogate."
UNKNOWN = "00000000-0000-4000-8000-000000000000"
WEEK = [1000] * 7
DAYS_REQUIRED = "Enter the target for every day."


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


def person(api: AuthApi, member: Member) -> Person:
    return Person(member.user_id, organization(api), "", "", "", "", "")


async def company(api: AuthApi, member: Member, name: str) -> str:
    response = await api.client.post(
        "/setup/companies", json={"name": name}, headers=member.headers
    )
    return str(ok(response)["id"])


def vehicle_body(company_id: str, **changes: Any) -> dict[str, Any]:
    """A vehicle save; the fleet number defaults to the registration's last four characters."""
    body: dict[str, Any] = {
        "companyId": company_id,
        "registration": "KDA 482M",
        "joinedOn": "2026-10-01",
        "dayTargets": WEEK,
    }
    body.update(changes)
    if "fleetNumber" not in changes:
        registration = str(body["registration"] or "N-1")
        body["fleetNumber"] = registration.replace(" ", "")[-4:].upper()
    return body


async def targets(
    api: AuthApi, member: Member, vehicle: str, starts_on: str, days: list[Any]
) -> dict[str, Any]:
    response = await api.client.post(
        f"/setup/vehicles/{vehicle}/targets",
        json={"startsOn": starts_on, "days": days},
        headers=member.headers,
    )
    result: dict[str, Any] = ok(response)
    return result


async def add(api: AuthApi, member: Member, company_id: str, **changes: Any) -> str:
    response = await api.client.post(
        "/setup/vehicles", json=vehicle_body(company_id, **changes), headers=member.headers
    )
    body = ok(response)
    assert list(body) == ["id"]
    return str(body["id"])


async def change(
    api: AuthApi, member: Member, vehicle: str, company_id: str, **changes: Any
) -> dict[str, Any]:
    response = await api.client.put(
        f"/setup/vehicles/{vehicle}",
        json=vehicle_body(company_id, **changes),
        headers=member.headers,
    )
    result: dict[str, Any] = ok(response)
    return result


async def lifecycle(
    api: AuthApi, member: Member, vehicle: str, action: str, **body: Any
) -> dict[str, Any]:
    response = await api.client.post(
        f"/setup/vehicles/{vehicle}/{action}", json=body, headers=member.headers
    )
    result: dict[str, Any] = ok(response)
    return result


async def entries(api: AuthApi, member: Member) -> list[dict[str, Any]]:
    """The vehicle change log, newest first."""
    page = ok(
        await api.client.get("/setup/history?section=vehicles&pageSize=100", headers=member.headers)
    )
    items: list[dict[str, Any]] = page["items"]
    return items


async def reasons(api: AuthApi, member: Member) -> list[str]:
    return [entry["reason"] for entry in reversed(await entries(api, member))]


async def manager_of(
    api: AuthApi, *, companies: tuple[str, ...] = (), vehicles: tuple[str, ...] = ()
) -> Member:
    """A fleet manager allowed to view, add and edit vehicles, but only within the scope given."""
    member = await join(api, email="sam@example.com", phone="0733000111", role="Fleet manager")
    for right in ("vehicles.view", "vehicles.add", "vehicles.edit"):
        set_override(api.owner, person(api, member), right)
    set_scope(
        api.owner,
        member.user_id,
        organization(api),
        companies=[UUID(c) for c in companies],
        vehicles=[UUID(v) for v in vehicles],
    )
    return member


async def viewer(api: AuthApi) -> Member:
    member = await join(api, email="vic@example.com", phone="0744000111", role="Revenue clerk")
    set_override(api.owner, person(api, member), "reports.investment")
    set_scope(api.owner, member.user_id, organization(api), all_companies=True)
    return member


# --- list ------------------------------------------------------------------------------


async def test_the_list_carries_targets_scheduled_items_and_days_away_for_a_manager(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    south = await company(api, owner, "South Line")
    kda = await add(api, owner, north)
    kdb = await add(api, owner, south, registration="KDB 111A", dayTargets=[700] * 6 + [800])
    await lifecycle(api, owner, kda, "retire", leftOn="2026-10-03")
    await lifecycle(api, owner, kda, "restore")
    await targets(api, owner, kda, "2026-10-07", [1300] * 6 + [1200])
    await targets(api, owner, kda, "2026-10-20", [1400] * 6 + [1600.5])
    await lifecycle(api, owner, kdb, "retire", leftOn="2026-10-05")
    saving = {
        "name": "Owner savings",
        "kind": 2,
        "amount": 1000,
        "frequency": 2,
        "day": 5,
        "start": "2026-10-07",
        "allocations": [{"vehicleId": kda, "amount": 1000}],
    }
    ok(await api.client.post("/setup/recurring", json=saving, headers=owner.headers))
    response, count = await statements(api.client.get("/setup/vehicles", headers=owner.headers))
    page = ok(response)
    assert count == 2
    assert list(page) == ["items", "pageNumber", "pageSize", "total"]
    assert (page["pageNumber"], page["pageSize"], page["total"]) == (1, 25, 2)
    first, second = page["items"]
    assert list(first) == VEHICLE_KEYS
    assert first == {
        "id": kda,
        "companyId": north,
        "companyName": "North Star",
        "registration": "KDA 482M",
        "joinedOn": "2026-10-01",
        "leftOn": None,
        "active": True,
        "weeklyTarget": 9000,
        "targets": [
            {"effectiveFrom": "2026-10-01", "weeklyAmount": 7000, "revision": 1},
            {"effectiveFrom": "2026-10-07", "weeklyAmount": 9000, "revision": 2},
        ],
        "recurringItems": 1,
        "away": [{"leftOn": "2026-10-03", "returnedOn": "2026-10-07"}],
        "fleetNumber": "482M",
        "initialInvestment": None,
        "dayTargets": [1300] * 6 + [1200],
        "nextTarget": {
            "startsOn": "2026-10-20",
            "dayTargets": [1400] * 6 + [1600.5],
            "weeklyTarget": 10000.5,
        },
    }
    assert list(first["nextTarget"]) == ["startsOn", "dayTargets", "weeklyTarget"]
    assert [list(target) for target in first["targets"]] == [TARGET_KEYS, TARGET_KEYS]
    assert list(first["away"][0]) == AWAY_KEYS
    assert isinstance(first["weeklyTarget"], int)
    assert list(second) == VEHICLE_KEYS
    assert (second["id"], second["companyName"], second["leftOn"], second["active"]) == (
        kdb,
        "South Line",
        "2026-10-05",
        False,
    )
    assert (second["weeklyTarget"], second["recurringItems"], second["away"]) == (0, 0, [])
    assert second["targets"] == [
        {"effectiveFrom": "2026-10-01", "weeklyAmount": 5000, "revision": 1}
    ]
    assert (second["dayTargets"], second["nextTarget"]) == ([700] * 6 + [800], None)


async def test_the_list_shows_the_target_in_force_and_the_next_one(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north, dayTargets=[1000] * 5 + [1500, 500])
    (row,) = ok(await api.client.get("/setup/vehicles", headers=owner.headers))["items"]
    assert (row["weeklyTarget"], row["dayTargets"], row["nextTarget"]) == (
        7000,
        [1000] * 5 + [1500, 500],
        None,
    )
    await targets(api, owner, kda, "2026-10-12", [1200] * 7)
    (row,) = ok(await api.client.get("/setup/vehicles", headers=owner.headers))["items"]
    assert (row["weeklyTarget"], row["dayTargets"]) == (7000, [1000] * 5 + [1500, 500])
    assert row["nextTarget"] == {
        "startsOn": "2026-10-12",
        "dayTargets": [1200] * 7,
        "weeklyTarget": 8400,
    }
    assert [t["effectiveFrom"] for t in row["targets"]] == ["2026-10-01"]


async def test_an_investment_viewer_gets_no_targets_and_no_scheduled_item_count(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    vic = await viewer(api)
    response, count = await statements(api.client.get("/setup/vehicles", headers=vic.headers))
    page = ok(response)
    assert count == 2
    (row,) = page["items"]
    assert list(row) == VEHICLE_KEYS
    assert (row["id"], row["registration"], row["companyName"]) == (kda, "KDA 482M", "North Star")
    assert row["weeklyTarget"] is None
    assert row["targets"] == []
    assert row["recurringItems"] is None
    assert (row["dayTargets"], row["nextTarget"], row["fleetNumber"]) == (None, None, "482M")
    problem(
        await api.client.get("/setup/vehicles/company-options", headers=vic.headers), 403, FORBIDDEN
    )


async def test_the_list_is_by_registration_and_pages(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    for registration in ("KDC 300C", "KDA 100A", "KDB 200B"):
        await add(api, owner, north, registration=registration)
    page = ok(await api.client.get("/setup/vehicles?page=2&pageSize=2", headers=owner.headers))
    assert (page["pageNumber"], page["pageSize"], page["total"]) == (2, 2, 3)
    assert [item["registration"] for item in page["items"]] == ["KDC 300C"]


async def test_the_list_checks_the_permission_before_the_page(api: AuthApi, owner: Member) -> None:
    for query in ("page=0", "pageSize=101", "page=100001", "pageSize=0"):
        problem(
            await api.client.get(f"/setup/vehicles?{query}", headers=owner.headers),
            400,
            INVALID,
            PAGING,
        )
    assert (
        await api.client.get("/setup/vehicles?page=one", headers=owner.headers)
    ).status_code == 400
    assert (
        await api.client.get("/setup/vehicles?pageSize=x", headers=owner.headers)
    ).status_code == 400
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    problem(await api.client.get("/setup/vehicles?page=0", headers=clerk.headers), 403, FORBIDDEN)


async def test_a_scoped_manager_lists_only_the_vehicles_in_reach(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    south = await company(api, owner, "South Line")
    kda = await add(api, owner, north)
    await add(api, owner, south, registration="KDB 111A")
    sam = await manager_of(api, companies=(north,))
    page = ok(await api.client.get("/setup/vehicles", headers=sam.headers))
    assert [item["id"] for item in page["items"]] == [kda]


async def test_the_company_filter_counts_and_pages_its_matches_only(
    api: AuthApi, owner: Member
) -> None:
    fleet = await company(api, owner, "Filter Fleet")
    for registration in ("KFA 103F", "KFA 101F", "KFA 102F"):
        await add(api, owner, fleet, registration=registration)
    await add(api, owner, await company(api, owner, "Other Filter Fleet"), registration="KFA 100F")
    response, count = await statements(
        api.client.get(f"/setup/vehicles?companyId={fleet}&pageSize=2", headers=owner.headers)
    )
    first = ok(response)
    assert count == 2
    assert (first["total"], [v["registration"] for v in first["items"]]) == (
        3,
        ["KFA 101F", "KFA 102F"],
    )
    second = ok(
        await api.client.get(
            f"/setup/vehicles?companyId={fleet}&pageSize=2&page=2", headers=owner.headers
        )
    )
    assert [v["registration"] for v in second["items"]] == ["KFA 103F"]
    assert ok(await api.client.get("/setup/vehicles", headers=owner.headers))["total"] == 4
    unknown = ok(
        await api.client.get(f"/setup/vehicles?companyId={UNKNOWN}", headers=owner.headers)
    )
    assert (unknown["total"], unknown["items"]) == (0, [])
    malformed = await api.client.get("/setup/vehicles?companyId=north", headers=owner.headers)
    assert malformed.status_code == 400


async def test_text_postgresql_cannot_store_is_refused_before_the_routine(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    response, count = await statements(
        api.client.post(
            "/setup/vehicles",
            content=(
                f'{{"companyId":"{north}","registration":"KDA\\u0000482M","fleetNumber":"N-1",'
                '"joinedOn":"2026-10-01","dayTargets":[1000,1000,1000,1000,1000,1000,1000]}'
            ),
            headers={**owner.headers, "content-type": "application/json"},
        )
    )
    body = problem(response, 400, INVALID, UNSTORABLE)
    assert body["errors"] == {"body": [UNSTORABLE]}
    assert count == 0
    lone = await api.client.post(
        "/setup/vehicles",
        content=(
            f'{{"companyId":"{north}","registration":"KDA 482M","joinedOn":"2026-10-01",'
            '"fleetNumber":"N-1","dayTargets":[1000,1000,1000,1000,1000,1000,1000],'
            '"reason":"\\ud800"}'
        ),
        headers={**owner.headers, "content-type": "application/json"},
    )
    problem(lone, 400, INVALID, UNSTORABLE)
    report = await api.client.get(
        f"/setup/vehicles/{UNKNOWN}/report?period=week%00", headers=owner.headers
    )
    assert problem(report, 400, INVALID, UNSTORABLE)["errors"] == {"query.period": [UNSTORABLE]}
    assert await entries(api, owner) == []


# --- company options -------------------------------------------------------------------


async def test_the_company_options_are_the_companies_in_use_by_name(
    api: AuthApi, owner: Member
) -> None:
    south = await company(api, owner, "South Line")
    north = await company(api, owner, "North Star")
    old = await company(api, owner, "Old Line")
    ok(await api.client.post(f"/setup/companies/{old}/archive", json={}, headers=owner.headers))
    response, count = await statements(
        api.client.get("/setup/vehicles/company-options", headers=owner.headers)
    )
    options = ok(response)
    assert count == 2
    assert options == [
        {"id": north, "name": "North Star"},
        {"id": south, "name": "South Line"},
    ]
    assert [list(option) for option in options] == [["id", "name"], ["id", "name"]]
    sam = await manager_of(api, companies=(south,))
    scoped = ok(await api.client.get("/setup/vehicles/company-options", headers=sam.headers))
    assert scoped == [{"id": south, "name": "South Line"}]


# --- create ----------------------------------------------------------------------------


async def test_a_created_vehicle_has_its_registration_normalised_and_is_logged(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    response, count = await statements(
        api.client.post(
            "/setup/vehicles",
            json=vehicle_body(north, registration=" kda482m "),
            headers=owner.headers,
        )
    )
    created = ok(response)
    assert count == 2
    assert list(created) == ["id"]
    page = ok(await api.client.get("/setup/vehicles", headers=owner.headers))
    assert page["items"][0]["registration"] == "KDA 482M"
    (entry,) = await entries(api, owner)
    assert list(entry) == ENTRY_KEYS
    assert (entry["section"], entry["entityId"]) == ("vehicles", created["id"])
    assert entry["reason"] == (
        "Added vehicle KDA 482M, fleet number 482M, to North Star with a weekly target of "
        "KES 7,000 from 2026-10-01"
    )
    assert entry["actorName"] == "Jane Doe"
    assert entry["before"] == "null"
    week = ",".join(f'"{day}":1000' for day in DAY_NAMES)
    assert entry["after"] == (
        f'{{"Id":"{created["id"]}","Registration":"KDA 482M","FleetNumber":"482M",'
        f'"CompanyId":"{north}","JoinedOn":"2026-10-01","LeftOn":null,"InitialInvestment":null,'
        f'"TargetSets":[{{"StartsOn":"2026-10-01",{week}}}],"Away":[]}}'
    )


DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


async def test_an_initial_investment_is_stored_and_zero_is_empty(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    await add(api, owner, north, initialInvestment=2500000.5)
    await add(api, owner, north, registration="KDB 111A", initialInvestment=0)
    page = ok(await api.client.get("/setup/vehicles", headers=owner.headers))
    assert [row["initialInvestment"] for row in page["items"]] == [2500000.5, None]


async def test_a_fleet_number_used_in_the_company_is_refused(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    south = await company(api, owner, "South Line")
    await add(api, owner, north, fleetNumber="NS-07")
    problem(
        await api.client.post(
            "/setup/vehicles",
            json=vehicle_body(north, registration="KDB 111A", fleetNumber=" ns-07 "),
            headers=owner.headers,
        ),
        400,
        INVALID,
        "Fleet number ns-07 is already used in this PSV company.",
    )
    await add(api, owner, south, registration="KDB 111A", fleetNumber="NS-07")


async def test_a_fractional_target_is_a_json_number_and_a_typed_reason_follows(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    days = [1000] * 5 + [1150.5, 1000]
    await add(api, owner, north, dayTargets=days, reason="Bought at auction")
    row = ok(await api.client.get("/setup/vehicles", headers=owner.headers))["items"][0]
    assert row["weeklyTarget"] == 7150.5
    assert isinstance(row["weeklyTarget"], float)
    assert row["dayTargets"] == days
    assert await reasons(api, owner) == [
        "Added vehicle KDA 482M, fleet number 482M, to North Star with a weekly target of "
        "KES 7,150.50 from 2026-10-01. Reason: Bought at auction."
    ]


@pytest.mark.parametrize(
    ("changes", "detail"),
    [
        ({"registration": "KDA-482M"}, "Use the registration format KDA 482M."),
        ({"registration": None}, "Use the registration format KDA 482M."),
        ({"fleetNumber": None}, "Enter the fleet number."),
        ({"fleetNumber": "  "}, "Enter the fleet number."),
        ({"fleetNumber": "F" * 21}, "A fleet number has at most 20 characters."),
        ({"dayTargets": None, "weeklyTarget": 7000}, DAYS_REQUIRED),
        ({"dayTargets": WEEK[:6]}, DAYS_REQUIRED),
        ({"dayTargets": [*WEEK[:6], None]}, DAYS_REQUIRED),
        ({"dayTargets": [0, *WEEK[1:]]}, MONEY),
        ({"dayTargets": [-5, *WEEK[1:]]}, MONEY),
        ({"dayTargets": [1.005, *WEEK[1:]]}, MONEY),
        ({"dayTargets": [1000000000000, *WEEK[1:]]}, MONEY),
        ({"initialInvestment": -1}, MONEY),
        ({"initialInvestment": 1.005}, MONEY),
        ({"joinedOn": "2026-10-08"}, "A vehicle cannot join after the business date."),
        ({"joinedOn": None}, "A vehicle cannot join after the business date."),
        ({"reason": "x" * 501}, REASON_LENGTH),
    ],
)
async def test_a_malformed_vehicle_is_refused_with_its_sentence(
    api: AuthApi, owner: Member, changes: dict[str, Any], detail: str
) -> None:
    north = await company(api, owner, "North Star")
    response = await api.client.post(
        "/setup/vehicles", json=vehicle_body(north, **changes), headers=owner.headers
    )
    problem(response, 400, INVALID, detail)
    assert await entries(api, owner) == []


async def test_a_registration_that_exists_is_refused(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    south = await company(api, owner, "South Line")
    await add(api, owner, south)
    problem(
        await api.client.post(
            "/setup/vehicles",
            json=vehicle_body(north, registration="kda 482 m"),
            headers=owner.headers,
        ),
        400,
        INVALID,
        "This registration already exists.",
    )


async def test_a_vehicle_needs_a_company_in_reach_that_is_in_use(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    south = await company(api, owner, "South Line")
    old = await company(api, owner, "Old Line")
    ok(await api.client.post(f"/setup/companies/{old}/archive", json={}, headers=owner.headers))
    problem(
        await api.client.post("/setup/vehicles", json=vehicle_body(UNKNOWN), headers=owner.headers),
        404,
        NOT_FOUND,
    )
    problem(
        await api.client.post("/setup/vehicles", json=vehicle_body(old), headers=owner.headers),
        400,
        INVALID,
        "Choose an active PSV company.",
    )
    sam = await manager_of(api, companies=(north,))
    problem(
        await api.client.post("/setup/vehicles", json=vehicle_body(south), headers=sam.headers),
        404,
        NOT_FOUND,
    )
    await add(api, sam, north, registration="KDB 111A")
    page = ok(await api.client.get("/setup/vehicles", headers=owner.headers))
    assert [item["registration"] for item in page["items"]] == ["KDB 111A"]


async def test_a_vehicle_scope_cannot_create_a_vehicle(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    sam = await manager_of(api, vehicles=(kda,))
    problem(
        await api.client.post(
            "/setup/vehicles",
            json=vehicle_body(north, registration="KDB 111A"),
            headers=sam.headers,
        ),
        403,
        FORBIDDEN,
    )


# --- update ----------------------------------------------------------------------------


async def test_editing_a_vehicle_leaves_its_targets_alone(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    response, count = await statements(
        api.client.put(
            f"/setup/vehicles/{kda}",
            json=vehicle_body(
                north,
                fleetNumber="N-9",
                weeklyTarget=5000,
                dayTargets=[1] * 7,
                initialInvestment=150000,
            ),
            headers=owner.headers,
        )
    )
    assert ok(response) == {"id": kda}
    assert count == 2
    entry = (await entries(api, owner))[0]
    assert entry["reason"] == (
        "Changed the fleet number of KDA 482M to N-9; changed the initial investment of "
        "KDA 482M to KES 150,000"
    )
    assert (entry["section"], entry["entityId"]) == ("vehicles", kda)
    before, after = json.loads(entry["before"]), json.loads(entry["after"])
    assert before["TargetSets"] == after["TargetSets"]
    assert [s["StartsOn"] for s in after["TargetSets"]] == ["2026-10-01"]
    (row,) = ok(await api.client.get("/setup/vehicles", headers=owner.headers))["items"]
    assert (row["fleetNumber"], row["initialInvestment"], row["weeklyTarget"]) == (
        "N-9",
        150000,
        7000,
    )


async def test_moving_company_and_join_date_says_both(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    south = await company(api, owner, "South Line")
    kda = await add(api, owner, north)
    await change(api, owner, kda, south, joinedOn="2026-09-25", reason="Reassigned")
    assert (await reasons(api, owner))[-1] == (
        "Moved KDA 482M to South Line; changed when KDA 482M joined the fleet to 2026-09-25. "
        "Reason: Reassigned."
    )
    row = ok(await api.client.get("/setup/vehicles", headers=owner.headers))["items"][0]
    assert (row["companyId"], row["joinedOn"]) == (south, "2026-09-25")


async def test_an_update_that_changes_nothing_is_ok_and_leaves_no_history(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    before = await entries(api, owner)
    response, count = await statements(
        api.client.put(
            f"/setup/vehicles/{kda}",
            json=vehicle_body(north, registration="kda482m", weeklyTarget=9999),
            headers=owner.headers,
        )
    )
    assert ok(response) == {"id": kda}
    assert count == 2
    assert await entries(api, owner) == before


@pytest.mark.parametrize(
    ("changes", "detail"),
    [
        ({"registration": "KDB 111A"}, "Registration cannot change after a vehicle is added."),
        ({"registration": "KDA-482M"}, "Use the registration format KDA 482M."),
        ({"fleetNumber": None}, "Enter the fleet number."),
        ({"initialInvestment": 0.001}, MONEY),
        ({"joinedOn": "2026-10-08"}, "A vehicle cannot join after the business date."),
        ({"reason": "x" * 501}, REASON_LENGTH),
    ],
)
async def test_a_malformed_vehicle_update_is_refused_with_its_sentence(
    api: AuthApi, owner: Member, changes: dict[str, Any], detail: str
) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    response = await api.client.put(
        f"/setup/vehicles/{kda}", json=vehicle_body(north, **changes), headers=owner.headers
    )
    problem(response, 400, INVALID, detail)


async def test_a_retired_vehicle_must_be_restored_before_it_is_edited(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    await lifecycle(api, owner, kda, "retire", leftOn="2026-10-07")
    problem(
        await api.client.put(
            f"/setup/vehicles/{kda}", json=vehicle_body(north), headers=owner.headers
        ),
        400,
        INVALID,
        "Retired vehicles must be restored before they can be edited.",
    )


async def test_an_update_needs_a_company_in_use_and_in_reach(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    old = await company(api, owner, "Old Line")
    kda = await add(api, owner, north)
    ok(await api.client.post(f"/setup/companies/{old}/archive", json={}, headers=owner.headers))
    problem(
        await api.client.put(
            f"/setup/vehicles/{kda}", json=vehicle_body(old), headers=owner.headers
        ),
        400,
        INVALID,
        "Choose an active PSV company.",
    )
    problem(
        await api.client.put(
            f"/setup/vehicles/{kda}", json=vehicle_body(UNKNOWN), headers=owner.headers
        ),
        404,
        NOT_FOUND,
    )


async def test_the_join_date_cannot_move_past_a_day_with_revenue(
    api: AuthApi, owner: Member
) -> None:
    org = organization(api)
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    for day in (date(2026, 10, 3), date(2026, 10, 5)):
        add_record(api.owner, org, UUID(kda), day, 1500, recorder=owner.user_id)
    problem(
        await api.client.put(
            f"/setup/vehicles/{kda}",
            json=vehicle_body(north, joinedOn="2026-10-04"),
            headers=owner.headers,
        ),
        400,
        INVALID,
        "KDA 482M has revenue recorded on 2026-10-03. "
        "A vehicle cannot join the fleet after a day it has a record for.",
    )
    await change(api, owner, kda, north, joinedOn="2026-10-03")


# --- retire and restore ----------------------------------------------------------------


async def test_retiring_takes_the_vehicle_out_from_the_leave_date(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    response, count = await statements(
        api.client.post(
            f"/setup/vehicles/{kda}/retire",
            json={"leftOn": "2026-10-07", "reason": "Sold to the SACCO."},
            headers=owner.headers,
        )
    )
    assert ok(response) == {"id": kda}
    assert count == 2
    entry = (await entries(api, owner))[0]
    assert (
        entry["reason"]
        == "Vehicle KDA 482M left the fleet on 2026-10-07. Reason: Sold to the SACCO."
    )
    assert json.loads(entry["before"])["LeftOn"] is None
    assert json.loads(entry["after"])["LeftOn"] == "2026-10-07"
    row = ok(await api.client.get("/setup/vehicles", headers=owner.headers))["items"][0]
    assert (row["leftOn"], row["active"]) == ("2026-10-07", False)


async def test_retiring_again_on_the_same_day_is_ok_and_another_day_is_refused(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    await lifecycle(api, owner, kda, "retire", leftOn="2026-10-07")
    again, count = await statements(
        api.client.post(
            f"/setup/vehicles/{kda}/retire", json={"leftOn": "2026-10-07"}, headers=owner.headers
        )
    )
    assert ok(again) == {"id": kda}
    assert count == 2
    assert len(await entries(api, owner)) == 2
    problem(
        await api.client.post(
            f"/setup/vehicles/{kda}/retire", json={"leftOn": "2026-10-06"}, headers=owner.headers
        ),
        400,
        INVALID,
        "The vehicle is already retired.",
    )


@pytest.mark.parametrize("left_on", [None, "2026-10-08", "2026-09-30"])
async def test_a_leave_date_outside_join_and_business_date_is_refused(
    api: AuthApi, owner: Member, left_on: str | None
) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    problem(
        await api.client.post(
            f"/setup/vehicles/{kda}/retire", json={"leftOn": left_on}, headers=owner.headers
        ),
        400,
        INVALID,
        "A vehicle's leave date must be from its join date through the business date.",
    )


async def test_a_leave_date_on_or_before_a_recorded_day_is_refused(
    api: AuthApi, owner: Member
) -> None:
    org = organization(api)
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    for day in (date(2026, 10, 2), date(2026, 10, 4)):
        add_record(api.owner, org, UUID(kda), day, 1500, recorder=owner.user_id)
    problem(
        await api.client.post(
            f"/setup/vehicles/{kda}/retire", json={"leftOn": "2026-10-02"}, headers=owner.headers
        ),
        400,
        INVALID,
        "KDA 482M has revenue recorded on 2026-10-04. "
        "A vehicle cannot leave the fleet on or before a day it has a record for.",
    )
    assert await lifecycle(api, owner, kda, "retire", leftOn="2026-10-05") == {"id": kda}


async def test_a_second_leave_cannot_overlap_the_time_away(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    await lifecycle(api, owner, kda, "retire", leftOn="2026-10-03")
    await lifecycle(api, owner, kda, "restore", returnedOn="2026-10-05")
    problem(
        await api.client.post(
            f"/setup/vehicles/{kda}/retire", json={"leftOn": "2026-10-04"}, headers=owner.headers
        ),
        400,
        INVALID,
        "A vehicle's leave date must be on or after the day it last returned to the fleet.",
    )
    assert await lifecycle(api, owner, kda, "retire", leftOn="2026-10-05") == {"id": kda}


async def test_restoring_records_the_days_away_and_names_them(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    await lifecycle(api, owner, kda, "retire", leftOn="2026-10-03")
    response, count = await statements(
        api.client.post(f"/setup/vehicles/{kda}/restore", json={}, headers=owner.headers)
    )
    assert ok(response) == {"id": kda}
    assert count == 2
    entry = (await entries(api, owner))[0]
    assert entry["reason"] == (
        "Vehicle KDA 482M returned to the fleet on 2026-10-07; it was away from 2026-10-03 to "
        "2026-10-06"
    )
    assert json.loads(entry["after"])["Away"] == [
        {"LeftOn": "2026-10-03", "ReturnedOn": "2026-10-07"}
    ]
    row = ok(await api.client.get("/setup/vehicles", headers=owner.headers))["items"][0]
    assert (row["leftOn"], row["active"]) == (None, True)
    assert row["away"] == [{"leftOn": "2026-10-03", "returnedOn": "2026-10-07"}]


async def test_a_return_on_the_leave_date_records_no_time_away(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    await lifecycle(api, owner, kda, "retire", leftOn="2026-10-03")
    await lifecycle(api, owner, kda, "restore", returnedOn="2026-10-03", reason="Back.")
    assert (await reasons(api, owner))[-1] == (
        "Vehicle KDA 482M returned to the fleet on 2026-10-03. Reason: Back."
    )
    row = ok(await api.client.get("/setup/vehicles", headers=owner.headers))["items"][0]
    assert row["away"] == []


async def test_restoring_a_vehicle_in_the_fleet_is_ok_and_leaves_no_history(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    assert await lifecycle(api, owner, kda, "restore", returnedOn="2020-01-01") == {"id": kda}
    assert len(await entries(api, owner)) == 1


@pytest.mark.parametrize("returned_on", ["2026-10-02", "2026-10-08"])
async def test_a_return_outside_the_time_away_is_refused(
    api: AuthApi, owner: Member, returned_on: str
) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    await lifecycle(api, owner, kda, "retire", leftOn="2026-10-03")
    problem(
        await api.client.post(
            f"/setup/vehicles/{kda}/restore",
            json={"returnedOn": returned_on},
            headers=owner.headers,
        ),
        400,
        INVALID,
        "A vehicle's return date must be from the day it left through the business date.",
    )


async def test_a_vehicle_of_an_archived_company_cannot_be_restored(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    await lifecycle(api, owner, kda, "retire", leftOn="2026-10-03")
    ok(await api.client.post(f"/setup/companies/{north}/archive", json={}, headers=owner.headers))
    problem(
        await api.client.post(f"/setup/vehicles/{kda}/restore", json={}, headers=owner.headers),
        400,
        INVALID,
        "Restore the vehicle's archived company first.",
    )


async def test_lifecycle_routes_refuse_a_long_reason(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    problem(
        await api.client.post(
            f"/setup/vehicles/{kda}/retire",
            json={"leftOn": "2026-10-07", "reason": "x" * 501},
            headers=owner.headers,
        ),
        400,
        INVALID,
        REASON_LENGTH,
    )
    problem(
        await api.client.post(
            f"/setup/vehicles/{kda}/restore", json={"reason": "x" * 501}, headers=owner.headers
        ),
        400,
        INVALID,
        REASON_LENGTH,
    )


async def test_body_routes_require_a_json_body(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    text = {**owner.headers, "Content-Type": "text/plain"}
    payload = json.dumps(vehicle_body(north, registration="KDB 111A")).encode()
    empty(await api.client.post("/setup/vehicles", content=payload, headers=text), 415)
    empty(await api.client.post("/setup/vehicles", content=payload, headers=owner.headers), 415)
    empty(await api.client.put(f"/setup/vehicles/{kda}", content=payload, headers=text), 415)
    for action in ("retire", "restore"):
        path = f"/setup/vehicles/{kda}/{action}"
        empty(await api.client.post(path, headers=owner.headers), 415)
        empty(await api.client.post(path, content=b"{}", headers=text), 415)
        empty(await api.client.post(path, content=b"{}", headers=owner.headers), 415)
    malformed = await api.client.post(
        "/setup/vehicles",
        content=b"{not json",
        headers={**owner.headers, "Content-Type": "application/json"},
    )
    assert malformed.status_code == 400
    assert len(await entries(api, owner)) == 1


# --- not found, permissions and tokens -------------------------------------------------


async def test_an_unknown_or_out_of_scope_vehicle_is_not_found(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    south = await company(api, owner, "South Line")
    await add(api, owner, north)
    kdb = await add(api, owner, south, registration="KDB 111A")
    sam = await manager_of(api, companies=(north,))
    for member, vehicle in ((owner, UNKNOWN), (sam, kdb)):
        problem(
            await api.client.put(
                f"/setup/vehicles/{vehicle}",
                json=vehicle_body(north, registration="KDB 111A"),
                headers=member.headers,
            ),
            404,
            NOT_FOUND,
        )
        problem(
            await api.client.post(
                f"/setup/vehicles/{vehicle}/retire",
                json={"leftOn": "2026-10-07"},
                headers=member.headers,
            ),
            404,
            NOT_FOUND,
        )
        problem(
            await api.client.post(
                f"/setup/vehicles/{vehicle}/restore", json={}, headers=member.headers
            ),
            404,
            NOT_FOUND,
        )
        problem(
            await api.client.get(
                f"/setup/vehicles/{vehicle}/report?period=month", headers=member.headers
            ),
            404,
            NOT_FOUND,
        )


async def test_a_malformed_vehicle_id_is_an_empty_not_found(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    empty(
        await api.client.put(
            "/setup/vehicles/not-a-uuid", json=vehicle_body(north), headers=owner.headers
        ),
        404,
    )
    for action in ("retire", "restore"):
        empty(
            await api.client.post(
                f"/setup/vehicles/not-a-uuid/{action}", json={}, headers=owner.headers
            ),
            404,
        )
    empty(
        await api.client.get(
            "/setup/vehicles/not-a-uuid/report?period=week", headers=owner.headers
        ),
        404,
    )


async def test_vehicle_routes_need_the_vehicle_rights(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    problem(await api.client.get("/setup/vehicles", headers=clerk.headers), 403, FORBIDDEN)
    problem(
        await api.client.get("/setup/vehicles/company-options", headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.post("/setup/vehicles", json=vehicle_body(north), headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.put(
            f"/setup/vehicles/{kda}", json=vehicle_body(north), headers=clerk.headers
        ),
        403,
        FORBIDDEN,
    )
    for action in ("retire", "restore"):
        problem(
            await api.client.post(
                f"/setup/vehicles/{kda}/{action}", json={}, headers=clerk.headers
            ),
            403,
            FORBIDDEN,
        )
    problem(
        await api.client.get(f"/setup/vehicles/{kda}/report?period=week", headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    vic = await viewer(api)
    problem(
        await api.client.get(f"/setup/vehicles/{kda}/report?period=week", headers=vic.headers),
        403,
        FORBIDDEN,
    )
    looker = await join(api, email="lou@example.com", phone="0755000111", role="Revenue clerk")
    set_override(api.owner, person(api, looker), "vehicles.view")
    set_scope(api.owner, looker.user_id, organization(api), all_companies=True)
    assert ok(await api.client.get("/setup/vehicles", headers=looker.headers))["total"] == 1
    for method, path, body in [
        ("post", "/setup/vehicles", vehicle_body(north, registration="KDB 111A")),
        ("put", f"/setup/vehicles/{kda}", vehicle_body(north)),
        ("post", f"/setup/vehicles/{kda}/retire", {"leftOn": "2026-10-07"}),
    ]:
        problem(
            await api.client.request(method, path, json=body, headers=looker.headers),
            403,
            FORBIDDEN,
        )
    assert len(await entries(api, owner)) == 1


async def test_vehicle_options_carry_the_fleet_number(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north, fleetNumber="NS-07")
    options = ok(await api.client.get("/setup/recurring/vehicle-options", headers=owner.headers))
    assert [(o["id"], o["registration"], o["fleetNumber"]) for o in options] == [
        (kda, "KDA 482M", "NS-07")
    ]
    scope = ok(await api.client.get("/setup/access/scope-options", headers=owner.headers))
    assert scope["vehicles"] == [
        {"id": kda, "registration": "KDA 482M", "fleetNumber": "NS-07", "companyId": north}
    ]


async def test_vehicle_routes_need_a_token(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    kda = await add(api, owner, north)
    empty(await api.client.get("/setup/vehicles"), 401)
    empty(await api.client.get("/setup/vehicles/company-options"), 401)
    empty(await api.client.post("/setup/vehicles", json=vehicle_body(north)), 401)
    empty(await api.client.put(f"/setup/vehicles/{kda}", json=vehicle_body(north)), 401)
    for action in ("retire", "restore"):
        empty(await api.client.post(f"/setup/vehicles/{kda}/{action}", json={}), 401)
    empty(await api.client.get(f"/setup/vehicles/{kda}/report?period=week"), 401)


# --- report ----------------------------------------------------------------------------


@pytest.fixture
async def fleet(api: AuthApi, owner: Member) -> ReportFleet:
    org = organization(api)
    set_organization(api.owner, org, business_date=date(2026, 3, 31))
    return seed_report_fleet(api.owner, org, owner.user_id)


async def test_the_report_counts_money_in_the_target_each_bucket_and_savings_once(
    api: AuthApi, owner: Member, fleet: ReportFleet
) -> None:
    response, count = await statements(
        api.client.get(
            f"/setup/vehicles/{fleet.kda}/report?from=2026-03-01&through=2026-03-31",
            headers=owner.headers,
        )
    )
    report = ok(response)
    assert count == 2
    assert list(report) == REPORT_KEYS
    postings = report.pop("postings")
    assert report == {
        "vehicleId": str(fleet.kda),
        "from": "2026-03-01",
        "through": "2026-03-31",
        "moneyIn": 43500,
        "target": 45000,
        "repairs": 5000,
        "charges": 7150,
        "loans": 10000,
        "moneyOut": 22150,
        "net": 21350,
        "savings": 4000,
        "afterSavings": 17350,
        "costs": 22150,
    }
    assert all(type(report[key]) is int for key in REPORT_KEYS[3:-1])
    assert [list(posting) for posting in postings] == [POSTING_KEYS] * len(postings)
    assert [
        (p["date"], p["name"], p["kind"], p["amount"], p["bucket"]) for p in postings
    ] == MARCH_POSTINGS
    items = {name: str(item) for name, item in fleet.items.items()}
    assert all(p["itemId"] == items[p["name"]] for p in postings)
    assert all(UUID(p["versionId"]) for p in postings)
    assert all(p["source"] is None for p in postings)


async def test_a_month_report_runs_from_the_first_through_today(
    api: AuthApi, owner: Member, fleet: ReportFleet
) -> None:
    add_record(
        api.owner, organization(api), fleet.kda, date(2026, 3, 31), 2000, recorder=owner.user_id
    )
    month = ok(
        await api.client.get(
            f"/setup/vehicles/{fleet.kda}/report?period=month", headers=owner.headers
        )
    )
    assert (month["from"], month["through"]) == ("2026-03-01", "2026-03-31")
    assert (month["moneyIn"], month["target"], month["net"]) == (45500, 47000, 23350)
    with_range = ok(
        await api.client.get(
            f"/setup/vehicles/{fleet.kda}/report?period=month&from=2020-01-01&through=2020-02-01",
            headers=owner.headers,
        )
    )
    assert (with_range["from"], with_range["through"]) == ("2026-03-01", "2026-03-31")


async def test_a_week_report_runs_from_the_first_day_of_the_week_through_today(
    api: AuthApi, owner: Member, fleet: ReportFleet
) -> None:
    week = ok(
        await api.client.get(
            f"/setup/vehicles/{fleet.kda}/report?period=week", headers=owner.headers
        )
    )
    assert (week["from"], week["through"]) == ("2026-03-30", "2026-03-31")
    assert (week["moneyIn"], week["target"], week["loans"], week["net"]) == (0, 2000, 10000, -10000)
    assert [(p["date"], p["name"], p["amount"]) for p in week["postings"]] == [
        ("2026-03-31", "Loan repayment", 10000)
    ]


async def test_the_report_window_starts_at_the_join_date(
    api: AuthApi, owner: Member, fleet: ReportFleet
) -> None:
    january = ok(
        await api.client.get(
            f"/setup/vehicles/{fleet.kda}/report?from=2026-01-01&through=2026-02-03",
            headers=owner.headers,
        )
    )
    assert (january["from"], january["through"]) == ("2026-01-01", "2026-02-03")
    assert (january["target"], january["postings"][0]["date"]) == (3000, "2026-02-02")


@pytest.mark.parametrize(
    ("query", "detail"),
    [
        ("period=day", "Period must be week or month."),
        ("period=Week", "Period must be week or month."),
        ("", "Choose a period, or a from and through date."),
        ("from=2026-03-01", "Choose a period, or a from and through date."),
        ("through=2026-03-01", "Choose a period, or a from and through date."),
        (
            "from=2026-03-02&through=2026-03-01",
            "Report range must be at most 367 days and cannot include the future.",
        ),
        (
            "from=2025-03-03&through=2026-03-31",
            "Report range must be at most 367 days and cannot include the future.",
        ),
        (
            "from=2026-03-01&through=2026-04-01",
            "Report range must be at most 367 days and cannot include the future.",
        ),
    ],
)
async def test_the_report_refuses_a_bad_period_or_range(
    api: AuthApi, owner: Member, fleet: ReportFleet, query: str, detail: str
) -> None:
    response = await api.client.get(
        f"/setup/vehicles/{fleet.kda}/report?{query}", headers=owner.headers
    )
    problem(response, 400, INVALID, detail)


async def test_a_report_date_that_does_not_parse_is_a_400(
    api: AuthApi, owner: Member, fleet: ReportFleet
) -> None:
    for query in ("from=yesterday&through=2026-03-01", "from=2026-03-01&through=2026-13-45"):
        response = await api.client.get(
            f"/setup/vehicles/{fleet.kda}/report?{query}", headers=owner.headers
        )
        assert response.status_code == 400


async def test_a_range_of_367_days_is_accepted(
    api: AuthApi, owner: Member, fleet: ReportFleet
) -> None:
    report = ok(
        await api.client.get(
            f"/setup/vehicles/{fleet.kda}/report?from=2025-03-30&through=2026-03-31",
            headers=owner.headers,
        )
    )
    assert (report["from"], report["through"]) == ("2025-03-30", "2026-03-31")
