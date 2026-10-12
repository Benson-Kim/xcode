"""The access routes against the real database (``docs/06-http-contract.md`` section 2.2):
the catalogue every member reads, roles and scope options behind their permissions, the
caller's own scope; the property names the clients read, the problem bodies of refusals, the
uniform 401, the request id, the security headers and the statement budget of 2."""

from __future__ import annotations

import pytest

from ..support.client import ApiFactory, AuthApi
from ..support.setup_client import FORBIDDEN, Member, empty, join, ok, problem, statements

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


@pytest.fixture
async def clerk(api: AuthApi, owner: Member) -> Member:
    return await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")


async def test_every_member_reads_the_catalogue_in_its_shape(api: AuthApi, clerk: Member) -> None:
    response, count = await statements(
        api.client.get("/setup/access/catalog", headers=clerk.headers)
    )
    groups = ok(response)
    assert count == 2
    assert [group["name"] for group in groups] == [
        "Dashboard",
        "Revenue",
        "Central expenses",
        "Petty cash",
        "Scheduled expenses",
        "Savings",
        "Reports",
        "PSV companies",
        "Vehicles",
        "Expense items",
        "People and access",
        "Change log",
    ]
    for group in groups:
        assert list(group) == ["name", "items"]
        for item in group["items"]:
            assert list(item) == ["key", "label", "needs", "section"]
    keys = [item["key"] for group in groups for item in group["items"]]
    assert len(keys) == 59
    for key in ("revenue.capture", "pettycash.approve_item", "people.sign_in", "catalog.stop"):
        assert key in keys
    for key in ("bills.view", "dash.edits", "vehicles.manage", "organization.manage"):
        assert key not in keys
    items = {i["key"]: i for g in groups for i in g["items"]}
    assert items["dash.net"]["needs"] == ["revenue.view"]
    assert (items["pettycash.issue"]["section"], items["revenue.view"]["section"]) == ("Cash", None)


async def test_roles_need_people_view_and_list_by_name(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    response, count = await statements(api.client.get("/setup/access/roles", headers=owner.headers))
    roles = ok(response)
    assert count == 2
    assert [role["name"] for role in roles] == [
        "Fleet manager",
        "Office admin",
        "Owner",
        "Revenue clerk",
    ]
    assert all(list(role) == ["id", "name", "permissions"] for role in roles)
    assert roles[3]["permissions"] == ["dash.gaps", "revenue.view", "revenue.capture"]
    assert len(roles[2]["permissions"]) == 59
    refused = await api.client.get("/setup/access/roles", headers=clerk.headers)
    problem(refused, 403, FORBIDDEN)


async def test_scope_options_need_adding_or_editing_people(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    response, count = await statements(
        api.client.get("/setup/access/scope-options", headers=owner.headers)
    )
    assert ok(response) == {"companies": [], "vehicles": []}
    assert count == 2
    problem(
        await api.client.get("/setup/access/scope-options", headers=clerk.headers), 403, FORBIDDEN
    )


async def test_my_scope_lists_the_callers_own_reach(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    mine = ok(await api.client.get("/setup/access/me", headers=owner.headers))
    assert mine == {
        "allCompanies": True,
        "companies": [],
        "vehicles": [],
        "canChange": "Any date",
        "earliest": None,
    }
    theirs = ok(await api.client.get("/setup/access/me", headers=clerk.headers))
    assert list(theirs) == ["allCompanies", "companies", "vehicles", "canChange", "earliest"]
    assert theirs["allCompanies"] is False


@pytest.mark.parametrize(
    "path",
    [
        "/setup/access/catalog",
        "/setup/access/roles",
        "/setup/access/scope-options",
        "/setup/access/me",
    ],
)
async def test_an_anonymous_caller_gets_the_uniform_401(api: AuthApi, path: str) -> None:
    response = await api.client.get(path)
    empty(response, 401)
    assert response.headers["www-authenticate"] == "Bearer"
    garbled = await api.client.get(path, headers={"Authorization": "Bearer not-a-token"})
    empty(garbled, 401)


async def test_the_request_id_is_echoed_and_copied_into_problems(
    api: AuthApi, clerk: Member
) -> None:
    headers = {**clerk.headers, "X-Request-ID": "trace-access-1"}
    response = await api.client.get("/setup/access/roles", headers=headers)
    assert response.headers["x-request-id"] == "trace-access-1"
    assert problem(response, 403, FORBIDDEN)["requestId"] == "trace-access-1"
