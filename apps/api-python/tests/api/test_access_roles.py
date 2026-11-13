"""The custom role routes against the real database (``docs/06-http-contract.md`` rows S02 and
S65 to S67): roles list built-in first with ``builtIn`` and ``version``; a custom role is added,
renamed and re-granted at its version (409 only for a stale one, 400 for a name clash or a
built-in role) and deleted while nobody holds it; changing it ends its holders' sessions;
without ``access.manage`` the writes are 403, another organization's role is not found and
no token is 401."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from xcode_api.http.messages import IN_USE_TITLE

from ..support.client import ApiFactory, AuthApi, envelope
from ..support.rows import seed_organization
from ..support.setup_client import (
    FORBIDDEN,
    INVALID,
    NOT_FOUND,
    STALE,
    Member,
    empty,
    join,
    ok,
    problem,
    statements,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

ROLES = "/setup/access/roles"
CLERK_PHONE = "0744000111"
BUILT_IN = ["Owner", "Office admin", "Fleet manager", "Revenue clerk"]


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


@pytest.fixture
async def clerk(api: AuthApi, owner: Member) -> Member:
    return await join(api, email="clerk@example.com", phone=CLERK_PHONE, role="Revenue clerk")


async def _create(api: AuthApi, member: Member, name: str, permissions: list[str]) -> Any:
    return ok(
        await api.client.post(
            ROLES, json={"name": name, "permissions": permissions}, headers=member.headers
        )
    )


async def _roles(api: AuthApi, member: Member) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = ok(await api.client.get(ROLES, headers=member.headers))
    return roles


def _give(api: AuthApi, member: Member, role_id: str) -> None:
    api.owner.execute(
        "UPDATE tenancy.person_roles SET role_id = %s WHERE user_id = %s",
        (role_id, member.user_id),
    )


async def test_roles_list_built_in_first_with_their_version(api: AuthApi, owner: Member) -> None:
    created = await _create(api, owner, "Night clerk", ["revenue.capture"])
    assert created["builtIn"] is False
    assert created["version"] == 1
    assert created["permissions"] == ["revenue.view", "revenue.capture"]
    roles = await _roles(api, owner)
    assert [r["name"] for r in roles] == [*sorted(BUILT_IN, key=str.lower), "Night clerk"]
    assert [r["builtIn"] for r in roles] == [True] * 4 + [False]
    assert {r["version"] for r in roles} == {1}
    assert roles[-1] == created


async def test_a_role_is_created_changed_and_deleted_in_two_statements_each(
    api: AuthApi, owner: Member
) -> None:
    response, count = await statements(
        api.client.post(
            ROLES,
            json={"name": " Night clerk ", "permissions": ["revenue.view"], "builtIn": True},
            headers=owner.headers,
        )
    )
    role = ok(response)
    assert (role["name"], role["builtIn"], count) == ("Night clerk", False, 2)
    path = f"{ROLES}/{role['id']}"
    body = {"name": "Night shift", "permissions": ["revenue.capture"], "version": 1}
    response, count = await statements(api.client.put(path, json=body, headers=owner.headers))
    changed = ok(response)
    assert (changed["name"], changed["version"], count) == ("Night shift", 2, 2)
    assert changed["permissions"] == ["revenue.view", "revenue.capture"]
    same = ok(await api.client.put(path, json={**body, "version": 2}, headers=owner.headers))
    assert same == changed
    response, count = await statements(api.client.delete(path, headers=owner.headers))
    assert (ok(response), count) == ({"id": role["id"]}, 2)
    problem(await api.client.delete(path, headers=owner.headers), 404, NOT_FOUND)
    history = ok(
        await api.client.get("/setup/history?section=roles&pageSize=10", headers=owner.headers)
    )
    assert [entry["reason"] for entry in reversed(history["items"])] == [
        "Added role Night clerk",
        "Changed name and permissions of role Night shift",
        "Deleted role Night shift",
    ]


async def test_a_stale_version_is_the_only_409_on_a_change(api: AuthApi, owner: Member) -> None:
    role = await _create(api, owner, "Night clerk", ["revenue.view"])
    path = f"{ROLES}/{role['id']}"
    body = {"name": "Night clerk", "permissions": ["revenue.capture"], "version": 1}
    ok(await api.client.put(path, json=body, headers=owner.headers))
    problem(await api.client.put(path, json=body, headers=owner.headers), 409, STALE)
    await _create(api, owner, "Day clerk", ["revenue.view"])
    clash = {**body, "name": "DAY CLERK", "version": 2}
    problem(
        await api.client.put(path, json=clash, headers=owner.headers),
        400,
        INVALID,
        "Another role already has this name.",
    )


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        (
            {"name": " ", "permissions": ["revenue.view"]},
            "A role name of 1\u2013100 characters is required.",
        ),
        (
            {"name": "x" * 101, "permissions": ["revenue.view"]},
            "A role name of 1\u2013100 characters is required.",
        ),
        ({"name": "Night", "permissions": []}, "Choose at least one permission, each once."),
        (
            {"name": "Night", "permissions": ["revenue.view", "revenue.view"]},
            "Choose at least one permission, each once.",
        ),
        (
            {"name": "Night", "permissions": ["organization.manage"]},
            "A role can only have permissions from the list.",
        ),
        (
            {"name": "Night", "permissions": ["people.manage"]},
            "A role can only have permissions from the list.",
        ),
        ({"name": "owner", "permissions": ["revenue.view"]}, "Another role already has this name."),
    ],
)
async def test_a_role_the_rules_refuse_is_400_with_a_sentence(
    api: AuthApi, owner: Member, body: dict[str, Any], detail: str
) -> None:
    problem(await api.client.post(ROLES, json=body, headers=owner.headers), 400, INVALID, detail)
    assert [r["name"] for r in await _roles(api, owner)] == sorted(BUILT_IN, key=str.lower)


async def test_built_in_roles_cannot_be_changed_or_deleted(api: AuthApi, owner: Member) -> None:
    clerk_role = next(r for r in await _roles(api, owner) if r["name"] == "Revenue clerk")
    path = f"{ROLES}/{clerk_role['id']}"
    sentence = "Built-in roles cannot be changed or deleted."
    body = {"name": "Revenue clerk", "permissions": ["revenue.view"], "version": 1}
    problem(await api.client.put(path, json=body, headers=owner.headers), 400, INVALID, sentence)
    problem(await api.client.delete(path, headers=owner.headers), 400, INVALID, sentence)


async def test_a_role_someone_holds_is_not_deleted(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    role = await _create(api, owner, "Night clerk", ["revenue.view"])
    _give(api, clerk, role["id"])
    api.owner.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (clerk.user_id,)
    )
    response, count = await statements(
        api.client.delete(f"{ROLES}/{role['id']}", headers=owner.headers)
    )
    body = problem(
        response,
        409,
        IN_USE_TITLE,
        "Night clerk is held by 1 person: give them another role first.",
    )
    assert "people" not in body and count == 1
    assert [r["name"] for r in await _roles(api, owner)][-1] == "Night clerk"


async def test_changing_a_role_ends_its_holders_sessions_and_only_theirs(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    role = await _create(api, owner, "Night clerk", ["revenue.view"])
    _give(api, clerk, role["id"])
    problem(await api.client.get(ROLES, headers=clerk.headers), 403, FORBIDDEN)
    body = {"name": "Night clerk", "permissions": ["revenue.view", "people.view"], "version": 1}
    ok(await api.client.put(f"{ROLES}/{role['id']}", json=body, headers=owner.headers))
    empty(await api.client.get(ROLES, headers=clerk.headers), 401)
    ok(await api.client.get(ROLES, headers=owner.headers))
    tokens = envelope(
        await api.sign_in(phone=CLERK_PHONE, device=f"device-{CLERK_PHONE[-4:]}"),
        200,
        "authenticated",
    )
    again = Member(clerk.user_id, tokens)
    assert [r["name"] for r in ok(await api.client.get(ROLES, headers=again.headers))][-1] == (
        "Night clerk"
    )


async def test_the_caller_gives_and_changes_only_what_they_hold(
    api: AuthApi, owner: Member
) -> None:
    admin = await join(api, email="ada@example.com", phone="0733000111", role="Office admin")
    held = {r["name"]: r for r in await _roles(api, owner)}["Office admin"]["permissions"]
    beyond = next(
        key
        for key in {r["name"]: r for r in await _roles(api, owner)}["Owner"]["permissions"]
        if key not in held
    )
    problem(
        await api.client.post(
            ROLES, json={"name": "Wide", "permissions": [beyond]}, headers=admin.headers
        ),
        400,
        INVALID,
        "You can only give a role permissions you hold.",
    )
    wide = await _create(api, owner, "Wide", [beyond])
    path = f"{ROLES}/{wide['id']}"
    sentence = "You can only change or delete a role whose permissions you all hold."
    body = {"name": "Narrow", "permissions": [held[0]], "version": 1}
    problem(await api.client.put(path, json=body, headers=admin.headers), 400, INVALID, sentence)
    problem(await api.client.delete(path, headers=admin.headers), 400, INVALID, sentence)
    narrow = await _create(api, admin, "Narrow", [held[0]])
    assert narrow["builtIn"] is False


async def test_each_write_needs_access_manage(api: AuthApi, owner: Member, clerk: Member) -> None:
    role = await _create(api, owner, "Night clerk", ["revenue.view"])
    path = f"{ROLES}/{role['id']}"
    body = {"name": "Night", "permissions": ["revenue.view"], "version": 1}
    for response in (
        await api.client.get(ROLES, headers=clerk.headers),
        await api.client.post(ROLES, json=body, headers=clerk.headers),
        await api.client.put(path, json=body, headers=clerk.headers),
        await api.client.delete(path, headers=clerk.headers),
    ):
        problem(response, 403, FORBIDDEN)
    assert (await _roles(api, owner))[-1] == role


async def test_another_organizations_role_is_not_found_and_no_token_is_401(
    api: AuthApi, owner: Member
) -> None:
    other = seed_organization(api.owner)
    row = api.owner.execute(
        "SELECT id FROM tenancy.roles WHERE organization_id = %s LIMIT 1", (other.org,)
    ).fetchone()
    assert row is not None
    path = f"{ROLES}/{UUID(str(row['id']))}"
    body = {"name": "Night", "permissions": ["revenue.view"], "version": 1}
    problem(await api.client.put(path, json=body, headers=owner.headers), 404, NOT_FOUND)
    problem(await api.client.delete(path, headers=owner.headers), 404, NOT_FOUND)
    empty(await api.client.delete(f"{ROLES}/not-a-uuid", headers=owner.headers), 404)
    empty(await api.client.post(ROLES, json=body), 401)
    empty(await api.client.put(path, json=body), 401)
    empty(await api.client.delete(path), 401)
