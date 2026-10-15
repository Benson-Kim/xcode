"""The company routes against the real database (``docs/06-http-contract.md`` section 2.3): the
list in wire order with its vehicle counts and paging, create with its refusals and the
all-companies scope, rename (archived, taken, unchanged), archive (vehicles, same day, another
day) and restore, the change-log entries each write leaves with their exact reasons and JSON
text snapshots, the lifecycle routes that require a JSON body (415), the 401, 403 and 404
answers, and the statement budget of 2."""

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
from ..support.tenancy import add_company, add_vehicle, set_override, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

COMPANY_KEYS = ["id", "name", "vehicleCount", "active", "archivedOn"]
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


async def create(api: AuthApi, member: Member, name: str, **changes: Any) -> str:
    body = ok(
        await api.client.post(
            "/setup/companies", json={"name": name, **changes}, headers=member.headers
        )
    )
    assert list(body) == ["id"]
    return str(body["id"])


async def lifecycle(api: AuthApi, member: Member, company: str, action: str, **body: Any) -> Any:
    return ok(
        await api.client.post(
            f"/setup/companies/{company}/{action}", json=body, headers=member.headers
        )
    )


async def entries(api: AuthApi, member: Member) -> list[dict[str, Any]]:
    """The company change log, newest first."""
    page = ok(
        await api.client.get(
            "/setup/history?section=companies&pageSize=100", headers=member.headers
        )
    )
    items: list[dict[str, Any]] = page["items"]
    return items


async def reasons(api: AuthApi, member: Member) -> list[str]:
    return [entry["reason"] for entry in reversed(await entries(api, member))]


def snapshot(company: str, name: str, archived_on: str | None, active: bool) -> str:
    archived = "null" if archived_on is None else f'"{archived_on}"'
    return (
        f'{{"Id":"{company}","Name":"{name}","ArchivedOn":{archived},'
        f'"Active":{"true" if active else "false"}}}'
    )


async def manager_of(api: AuthApi, *companies: str) -> Member:
    """A fleet manager allowed to manage companies, but only the ones given."""
    member = await join(api, email="sam@example.com", phone="0733000111", role="Fleet manager")
    org = organization(api)
    for right in ("companies.view", "companies.add", "companies.edit"):
        set_override(api.owner, Person(member.user_id, org, "", "", "", "", ""), right)
    set_scope(api.owner, member.user_id, org, companies=[UUID(c) for c in companies])
    return member


async def test_the_company_list_is_in_wire_order_with_vehicle_counts(
    api: AuthApi, owner: Member
) -> None:
    org = organization(api)
    north = await create(api, owner, "North Star")
    south = await create(api, owner, "South Line")
    add_vehicle(api.owner, org, UUID(north), "KDA 482M")
    add_vehicle(api.owner, org, UUID(north), "KDB 111A")
    add_vehicle(api.owner, org, UUID(north), "KDC 200B", left_on=date(2026, 10, 1))
    await lifecycle(api, owner, south, "archive")
    response, count = await statements(api.client.get("/setup/companies", headers=owner.headers))
    page = ok(response)
    assert count == 2
    assert list(page) == ["items", "pageNumber", "pageSize", "total"]
    assert (page["pageNumber"], page["pageSize"], page["total"]) == (1, 25, 2)
    assert [list(item) for item in page["items"]] == [COMPANY_KEYS, COMPANY_KEYS]
    assert page["items"] == [
        {"id": north, "name": "North Star", "vehicleCount": 2, "active": True, "archivedOn": None},
        {
            "id": south,
            "name": "South Line",
            "vehicleCount": 0,
            "active": False,
            "archivedOn": "2026-10-07",
        },
    ]


async def test_the_company_list_pages_after_ordering_by_name(api: AuthApi, owner: Member) -> None:
    for name in ("Charlie", "Alpha", "Bravo"):
        await create(api, owner, name)
    page = ok(await api.client.get("/setup/companies?page=2&pageSize=1", headers=owner.headers))
    assert (page["pageNumber"], page["pageSize"], page["total"]) == (2, 1, 3)
    assert [item["name"] for item in page["items"]] == ["Bravo"]


async def test_the_company_list_refuses_a_page_out_of_range(api: AuthApi, owner: Member) -> None:
    for query in ("page=0", "pageSize=101", "page=100001", "pageSize=0"):
        problem(
            await api.client.get(f"/setup/companies?{query}", headers=owner.headers),
            400,
            INVALID,
            PAGING,
        )
    unparsable = await api.client.get("/setup/companies?page=one", headers=owner.headers)
    assert unparsable.status_code == 400
    unparsable = await api.client.get("/setup/companies?pageSize=1.5", headers=owner.headers)
    assert unparsable.status_code == 400


async def test_a_scoped_manager_lists_only_the_companies_in_reach(
    api: AuthApi, owner: Member
) -> None:
    north = await create(api, owner, "North Star")
    await create(api, owner, "South Line")
    sam = await manager_of(api, north)
    page = ok(await api.client.get("/setup/companies", headers=sam.headers))
    assert [(item["id"], item["name"]) for item in page["items"]] == [(north, "North Star")]
    assert page["total"] == 1


async def test_a_created_company_is_logged_with_its_snapshot(api: AuthApi, owner: Member) -> None:
    response, count = await statements(
        api.client.post("/setup/companies", json={"name": "  North Star "}, headers=owner.headers)
    )
    created = ok(response)
    assert count == 2
    assert list(created) == ["id"]
    (entry,) = await entries(api, owner)
    assert list(entry) == ENTRY_KEYS
    assert (entry["section"], entry["entityId"], entry["reason"]) == (
        "companies",
        created["id"],
        "Added company North Star",
    )
    assert entry["actorId"] == str(owner.user_id)
    assert entry["actorName"] == "Jane Doe"
    assert entry["before"] == "null"
    assert entry["after"] == snapshot(created["id"], "North Star", None, True)
    assert json.loads(entry["after"]) == {
        "Id": created["id"],
        "Name": "North Star",
        "ArchivedOn": None,
        "Active": True,
    }


async def test_a_typed_reason_follows_the_automatic_one(api: AuthApi, owner: Member) -> None:
    await create(api, owner, "North Star", reason="Signed with the SACCO")
    assert await reasons(api, owner) == ["Added company North Star. Reason: Signed with the SACCO."]


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"name": ""}, "Name must contain 1-160 characters."),
        ({"name": "   "}, "Name must contain 1-160 characters."),
        ({"name": "x" * 161}, "Name must contain 1-160 characters."),
        ({}, "Name must contain 1-160 characters."),
        ({"name": None}, "Name must contain 1-160 characters."),
        ({"name": "North", "reason": "x" * 501}, "A reason of 1\u2013500 characters is required."),
    ],
)
async def test_a_malformed_company_is_refused_with_its_sentence(
    api: AuthApi, owner: Member, body: dict[str, Any], detail: str
) -> None:
    problem(
        await api.client.post("/setup/companies", json=body, headers=owner.headers),
        400,
        INVALID,
        detail,
    )
    assert await entries(api, owner) == []


async def test_a_name_another_company_has_is_refused_ignoring_case(
    api: AuthApi, owner: Member
) -> None:
    await create(api, owner, "North Star")
    problem(
        await api.client.post(
            "/setup/companies", json={"name": "NORTH star"}, headers=owner.headers
        ),
        400,
        INVALID,
        "Another company already has this name.",
    )


async def test_creating_a_company_needs_every_company_in_reach(api: AuthApi, owner: Member) -> None:
    north = await create(api, owner, "North Star")
    sam = await manager_of(api, north)
    problem(
        await api.client.post("/setup/companies", json={"name": "South"}, headers=sam.headers),
        403,
        FORBIDDEN,
    )
    assert await reasons(api, owner) == ["Added company North Star"]


async def test_a_rename_is_logged_with_both_snapshots(api: AuthApi, owner: Member) -> None:
    company = await create(api, owner, "North Star")
    response, count = await statements(
        api.client.put(
            f"/setup/companies/{company}", json={"name": " North Line "}, headers=owner.headers
        )
    )
    assert ok(response) == {"id": company}
    assert count == 2
    entry = (await entries(api, owner))[0]
    assert entry["reason"] == "Renamed company North Star to North Line"
    assert (entry["section"], entry["entityId"]) == ("companies", company)
    assert entry["before"] == snapshot(company, "North Star", None, True)
    assert entry["after"] == snapshot(company, "North Line", None, True)
    page = ok(await api.client.get("/setup/companies", headers=owner.headers))
    assert [item["name"] for item in page["items"]] == ["North Line"]


async def test_renaming_with_a_typed_reason_appends_it(api: AuthApi, owner: Member) -> None:
    company = await create(api, owner, "North Star")
    ok(
        await api.client.put(
            f"/setup/companies/{company}",
            json={"name": "North Line", "reason": "New branding"},
            headers=owner.headers,
        )
    )
    assert (await reasons(api, owner))[-1] == (
        "Renamed company North Star to North Line. Reason: New branding."
    )


async def test_renaming_to_the_same_name_is_ok_and_leaves_no_history(
    api: AuthApi, owner: Member
) -> None:
    company = await create(api, owner, "North Star")
    before = await entries(api, owner)
    response, count = await statements(
        api.client.put(
            f"/setup/companies/{company}", json={"name": " North Star "}, headers=owner.headers
        )
    )
    assert ok(response) == {"id": company}
    assert count == 2
    assert await entries(api, owner) == before


async def test_a_rename_may_change_only_the_case_of_the_name(api: AuthApi, owner: Member) -> None:
    company = await create(api, owner, "North Star")
    ok(
        await api.client.put(
            f"/setup/companies/{company}", json={"name": "NORTH STAR"}, headers=owner.headers
        )
    )
    assert (await reasons(api, owner))[-1] == "Renamed company North Star to NORTH STAR"


async def test_a_rename_is_refused_for_a_taken_name_a_bad_name_and_a_long_reason(
    api: AuthApi, owner: Member
) -> None:
    company = await create(api, owner, "North Star")
    await create(api, owner, "South Line")
    path = f"/setup/companies/{company}"
    problem(
        await api.client.put(path, json={"name": "south line"}, headers=owner.headers),
        400,
        INVALID,
        "Another company already has this name.",
    )
    problem(
        await api.client.put(path, json={"name": " "}, headers=owner.headers),
        400,
        INVALID,
        "Name must contain 1-160 characters.",
    )
    problem(
        await api.client.put(
            path, json={"name": "North", "reason": "x" * 501}, headers=owner.headers
        ),
        400,
        INVALID,
        "A reason of 1\u2013500 characters is required.",
    )


async def test_an_archived_company_cannot_be_renamed(api: AuthApi, owner: Member) -> None:
    company = await create(api, owner, "North Star")
    await lifecycle(api, owner, company, "archive")
    problem(
        await api.client.put(
            f"/setup/companies/{company}", json={"name": "North Line"}, headers=owner.headers
        ),
        400,
        INVALID,
        "Archived companies cannot be renamed. Restore it first.",
    )


async def test_a_company_with_vehicles_in_the_fleet_cannot_be_archived(
    api: AuthApi, owner: Member
) -> None:
    org = organization(api)
    company = await create(api, owner, "North Star")
    add_vehicle(api.owner, org, UUID(company), "KDA 482M")
    problem(
        await api.client.post(
            f"/setup/companies/{company}/archive", json={}, headers=owner.headers
        ),
        400,
        INVALID,
        "Retire every vehicle in this company before archiving it.",
    )
    api.owner.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s WHERE company_id = %s",
        (date(2026, 10, 7), UUID(company)),
    )
    assert await lifecycle(api, owner, company, "archive") == {"id": company}


async def test_archiving_and_restoring_log_their_snapshots(api: AuthApi, owner: Member) -> None:
    company = await create(api, owner, "North Line")
    response, count = await statements(
        api.client.post(f"/setup/companies/{company}/archive", json={}, headers=owner.headers)
    )
    assert ok(response) == {"id": company}
    assert count == 2
    archived = (await entries(api, owner))[0]
    assert archived["reason"] == "Archived company North Line"
    assert archived["before"] == snapshot(company, "North Line", None, True)
    assert archived["after"] == snapshot(company, "North Line", "2026-10-07", False)
    response, count = await statements(
        api.client.post(f"/setup/companies/{company}/restore", json={}, headers=owner.headers)
    )
    assert ok(response) == {"id": company}
    assert count == 2
    restored = (await entries(api, owner))[0]
    assert restored["reason"] == "Restored company North Line"
    assert restored["before"] == archived["after"]
    assert restored["after"] == snapshot(company, "North Line", None, True)
    page = ok(await api.client.get("/setup/companies", headers=owner.headers))
    assert (page["items"][0]["active"], page["items"][0]["archivedOn"]) == (True, None)


async def test_a_typed_reason_follows_an_archive_and_a_restore(api: AuthApi, owner: Member) -> None:
    company = await create(api, owner, "North Line")
    await lifecycle(api, owner, company, "archive", reason="Merged into North Star")
    await lifecycle(api, owner, company, "restore", reason="Merger called off")
    assert (await reasons(api, owner))[1:] == [
        "Archived company North Line. Reason: Merged into North Star.",
        "Restored company North Line. Reason: Merger called off.",
    ]


async def test_repeating_an_archive_or_a_restore_is_ok_and_leaves_no_history(
    api: AuthApi, owner: Member
) -> None:
    company = await create(api, owner, "North Line")
    await lifecycle(api, owner, company, "archive")
    again, count = await statements(
        api.client.post(f"/setup/companies/{company}/archive", json={}, headers=owner.headers)
    )
    assert ok(again) == {"id": company}
    assert count == 2
    assert len(await entries(api, owner)) == 2
    await lifecycle(api, owner, company, "restore")
    again = await api.client.post(
        f"/setup/companies/{company}/restore", json={}, headers=owner.headers
    )
    assert ok(again) == {"id": company}
    assert len(await entries(api, owner)) == 3


async def test_an_archive_dated_another_day_is_refused_and_a_later_one_can_be_cancelled(
    api: AuthApi, owner: Member
) -> None:
    org = organization(api)
    earlier = str(add_company(api.owner, org, "Earlier", archived_on=date(2026, 10, 1)))
    later = str(add_company(api.owner, org, "Later", archived_on=date(2026, 10, 9)))
    for company in (earlier, later):
        problem(
            await api.client.post(
                f"/setup/companies/{company}/archive", json={}, headers=owner.headers
            ),
            400,
            INVALID,
            "The company is already archived.",
        )
    await lifecycle(api, owner, later, "restore", reason="Cancelled")
    assert await reasons(api, owner) == ["Restored company Later. Reason: Cancelled."]


async def test_lifecycle_routes_refuse_a_long_reason(api: AuthApi, owner: Member) -> None:
    company = await create(api, owner, "North Star")
    for action in ("archive", "restore"):
        problem(
            await api.client.post(
                f"/setup/companies/{company}/{action}",
                json={"reason": "x" * 501},
                headers=owner.headers,
            ),
            400,
            INVALID,
            "A reason of 1\u2013500 characters is required.",
        )


async def test_the_lifecycle_routes_require_a_json_body(api: AuthApi, owner: Member) -> None:
    company = await create(api, owner, "North Star")
    for action in ("archive", "restore"):
        path = f"/setup/companies/{company}/{action}"
        empty(await api.client.post(path, headers=owner.headers), 415)
        empty(await api.client.post(path, content=b"", headers=owner.headers), 415)
        empty(
            await api.client.post(
                path, content=b"{}", headers={**owner.headers, "Content-Type": "text/plain"}
            ),
            415,
        )
        empty(await api.client.post(path, content=b"{}", headers=owner.headers), 415)
    assert await reasons(api, owner) == ["Added company North Star"]
    assert await lifecycle(api, owner, company, "archive") == {"id": company}


async def test_a_body_route_without_json_is_415(api: AuthApi, owner: Member) -> None:
    company = await create(api, owner, "North Star")
    payload = json.dumps({"name": "North Line"}).encode()
    text = {**owner.headers, "Content-Type": "text/plain"}
    empty(await api.client.post("/setup/companies", content=payload, headers=text), 415)
    empty(await api.client.put(f"/setup/companies/{company}", content=payload, headers=text), 415)
    empty(
        await api.client.put(f"/setup/companies/{company}", content=payload, headers=owner.headers),
        415,
    )
    malformed = await api.client.post(
        "/setup/companies",
        content=b"{not json",
        headers={**owner.headers, "Content-Type": "application/json"},
    )
    assert malformed.status_code == 400


async def test_an_unknown_or_out_of_scope_company_is_not_found(api: AuthApi, owner: Member) -> None:
    north = await create(api, owner, "North Star")
    south = await create(api, owner, "South Line")
    sam = await manager_of(api, north)
    for member, company in ((owner, UNKNOWN), (sam, south)):
        problem(
            await api.client.put(
                f"/setup/companies/{company}", json={"name": "Renamed"}, headers=member.headers
            ),
            404,
            NOT_FOUND,
        )
        for action in ("archive", "restore"):
            problem(
                await api.client.post(
                    f"/setup/companies/{company}/{action}", json={}, headers=member.headers
                ),
                404,
                NOT_FOUND,
            )
    assert await reasons(api, owner) == ["Added company North Star", "Added company South Line"]


async def test_a_malformed_company_id_is_an_empty_not_found(api: AuthApi, owner: Member) -> None:
    empty(
        await api.client.put(
            "/setup/companies/not-a-uuid", json={"name": "X"}, headers=owner.headers
        ),
        404,
    )
    for action in ("archive", "restore"):
        empty(
            await api.client.post(
                f"/setup/companies/not-a-uuid/{action}", json={}, headers=owner.headers
            ),
            404,
        )


async def test_the_name_is_checked_before_the_company_is_found(api: AuthApi, owner: Member) -> None:
    problem(
        await api.client.put(
            f"/setup/companies/{UNKNOWN}", json={"name": ""}, headers=owner.headers
        ),
        400,
        INVALID,
        "Name must contain 1-160 characters.",
    )


async def test_company_routes_need_the_company_rights(api: AuthApi, owner: Member) -> None:
    company = await create(api, owner, "North Star")
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    problem(await api.client.get("/setup/companies", headers=clerk.headers), 403, FORBIDDEN)
    problem(
        await api.client.post("/setup/companies", json={"name": "X"}, headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.put(
            f"/setup/companies/{company}", json={"name": "X"}, headers=clerk.headers
        ),
        403,
        FORBIDDEN,
    )
    for action in ("archive", "restore"):
        problem(
            await api.client.post(
                f"/setup/companies/{company}/{action}", json={}, headers=clerk.headers
            ),
            403,
            FORBIDDEN,
        )
    assert await reasons(api, owner) == ["Added company North Star"]


async def test_company_routes_need_a_token(api: AuthApi, owner: Member) -> None:
    company = await create(api, owner, "North Star")
    empty(await api.client.get("/setup/companies"), 401)
    empty(await api.client.post("/setup/companies", json={"name": "X"}), 401)
    empty(await api.client.put(f"/setup/companies/{company}", json={"name": "X"}), 401)
    for action in ("archive", "restore"):
        empty(await api.client.post(f"/setup/companies/{company}/{action}", json={}), 401)
