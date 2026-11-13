"""Who may call the custom role routes and ``DELETE /setup/people/{id}`` (rows S02 and S65 to
S68), beyond what ``test_access_roles`` and ``test_person_delete`` prove: a ``people.view``
holder lists roles and changes nothing; a custom role holder with ``people.edit`` can neither
widen its own role, rename it to a built-in name nor touch a built-in role or one it does not
fully hold; no derived or hidden key goes into a role; a role body cannot choose its id,
organization, kind or version; a blocked member, a member whose membership ended and an
expired token are refused on all five routes; other methods, a method-override header and a
delete-shaped body never delete; and deleting a person needs the block permission, as erasing
one does."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from xcode_api.domain.tenancy import ORGANIZATION_MANAGE, RetiredPermission

from ..support.client import ApiFactory, AuthApi
from ..support.rows import seed_organization
from ..support.setup_client import FORBIDDEN, INVALID, Member, empty, join, ok, problem
from .test_invitations import invite

pytestmark = pytest.mark.asyncio(loop_scope="session")

ROLES = "/setup/access/roles"
PEOPLE = "/setup/people"
BUILT_IN = ["Owner", "Office admin", "Fleet manager", "Revenue clerk"]
GIVE_HELD = "You can only give a role permissions you hold."
CHANGE_HELD = "You can only change or delete a role whose permissions you all hold."
BUILT_IN_FIXED = "Built-in roles cannot be changed or deleted."
NAME_TAKEN = "Another role already has this name."
FROM_LIST = "A role can only have permissions from the list."
SELF = "You cannot delete yourself."
OWNER_EDIT = "Only an Owner can change, remove or sign out an Owner."
HIDDEN_KEYS = [*(key.value for key in RetiredPermission), ORGANIZATION_MANAGE]


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


@pytest.fixture
async def clerk(api: AuthApi, owner: Member) -> Member:
    return await join(api, email="clerk@example.com", phone="0744000111", role="Revenue clerk")


@pytest.fixture
async def admin(api: AuthApi, owner: Member) -> Member:
    return await join(api, email="ada@example.com", phone="0733000111", role="Office admin")


async def _create(
    api: AuthApi, member: Member, name: str, permissions: list[str]
) -> dict[str, Any]:
    role: dict[str, Any] = ok(
        await api.client.post(
            ROLES, json={"name": name, "permissions": permissions}, headers=member.headers
        )
    )
    return role


async def _roles(api: AuthApi, member: Member) -> dict[str, dict[str, Any]]:
    return {role["name"]: role for role in ok(await api.client.get(ROLES, headers=member.headers))}


def _give(api: AuthApi, member: Member, role_id: str) -> None:
    api.owner.execute(
        "UPDATE tenancy.person_roles SET role_id = %s WHERE user_id = %s",
        (role_id, member.user_id),
    )


def _organization_of_role(api: AuthApi, role_id: str) -> UUID | None:
    row = api.owner.execute(
        "SELECT organization_id FROM tenancy.roles WHERE id = %s", (role_id,)
    ).fetchone()
    return None if row is None else UUID(str(row["organization_id"]))


def _organization_of(api: AuthApi, member: Member) -> UUID:
    row = api.owner.execute(
        "SELECT organization_id FROM tenancy.memberships WHERE user_id = %s", (member.user_id,)
    ).fetchone()
    assert row is not None
    return UUID(str(row["organization_id"]))


def _person_exists(api: AuthApi, person_id: object) -> bool:
    row = api.owner.execute(
        "SELECT count(*) AS n FROM tenancy.memberships WHERE user_id = %s", (person_id,)
    ).fetchone()
    return row is not None and int(row["n"]) == 1


def _untouched(api: AuthApi, role: dict[str, Any], person_id: str) -> None:
    row = api.owner.execute(
        "SELECT name, version, (SELECT count(*) FROM tenancy.roles WHERE name = 'Night') AS added"
        " FROM tenancy.roles WHERE id = %s",
        (role["id"],),
    ).fetchone()
    assert row is not None
    assert (row["name"], int(row["version"]), int(row["added"])) == (role["name"], 1, 0)
    assert _person_exists(api, person_id)


async def _five_routes(
    api: AuthApi, headers: dict[str, str], role_id: str, person_id: str
) -> list[httpx.Response]:
    """GET, POST, PUT and DELETE of the role routes, then DELETE of the person."""
    body = {"name": "Night", "permissions": ["revenue.view"], "version": 1}
    calls: list[tuple[str, str, dict[str, Any] | None]] = [
        ("GET", ROLES, None),
        ("POST", ROLES, body),
        ("PUT", f"{ROLES}/{role_id}", body),
        ("DELETE", f"{ROLES}/{role_id}", None),
        ("DELETE", f"{PEOPLE}/{person_id}", None),
    ]
    return [
        await api.client.request(method, path, json=payload, headers=headers)
        for method, path, payload in calls
    ]


async def test_a_people_view_holder_lists_roles_and_changes_nothing(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    viewer = await _create(api, owner, "Viewer", ["people.view"])
    target = await _create(api, owner, "Night clerk", ["revenue.view"])
    person = await invite(api, owner)
    _give(api, clerk, viewer["id"])

    listed, *writes = await _five_routes(api, clerk.headers, target["id"], person)

    assert {r["name"] for r in ok(listed)} == {*BUILT_IN, "Night clerk", "Viewer"}
    for response in writes:
        problem(response, 403, FORBIDDEN)
    _untouched(api, target, person)


async def test_a_custom_role_holder_cannot_widen_its_role_or_reach_beyond_it(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    editor = await _create(api, owner, "Editor", ["people.edit"])
    wide = await _create(api, owner, "Wide", ["revenue.capture"])
    _give(api, clerk, editor["id"])
    built_in = (await _roles(api, clerk))["Owner"]
    own = f"{ROLES}/{editor['id']}"
    widened = {
        "name": "Editor",
        "permissions": [*editor["permissions"], "revenue.capture"],
        "version": 1,
    }

    problem(await api.client.put(own, json=widened, headers=clerk.headers), 400, INVALID, GIVE_HELD)
    problem(
        await api.client.post(ROLES, json={**widened, "name": "Editor 2"}, headers=clerk.headers),
        400,
        INVALID,
        GIVE_HELD,
    )
    renamed = {"name": "OWNER", "permissions": editor["permissions"], "version": 1}
    problem(
        await api.client.put(own, json=renamed, headers=clerk.headers), 400, INVALID, NAME_TAKEN
    )
    body = {"name": "Mine", "permissions": editor["permissions"], "version": 1}
    for path, sentence in (
        (f"{ROLES}/{built_in['id']}", BUILT_IN_FIXED),
        (f"{ROLES}/{wide['id']}", CHANGE_HELD),
    ):
        problem(
            await api.client.put(path, json=body, headers=clerk.headers), 400, INVALID, sentence
        )
        problem(await api.client.delete(path, headers=clerk.headers), 400, INVALID, sentence)

    roles = await _roles(api, clerk)
    assert (roles["Editor"], roles["Wide"], roles["Owner"]) == (editor, wide, built_in)
    assert (await _create(api, clerk, "Helper", ["people.edit"]))["builtIn"] is False


async def test_no_derived_or_hidden_key_goes_into_a_role(api: AuthApi, owner: Member) -> None:
    role = await _create(api, owner, "Night clerk", ["revenue.view"])
    path = f"{ROLES}/{role['id']}"
    for key in HIDDEN_KEYS:
        body = {"name": "Night clerk", "permissions": ["revenue.view", key], "version": 1}
        problem(
            await api.client.post(ROLES, json=body, headers=owner.headers), 400, INVALID, FROM_LIST
        )
        problem(
            await api.client.put(path, json=body, headers=owner.headers), 400, INVALID, FROM_LIST
        )
    roles = await _roles(api, owner)
    assert set(roles) == {*BUILT_IN, "Night clerk"}
    assert roles["Night clerk"] == role


async def test_a_role_body_cannot_choose_its_id_organization_kind_or_version(
    api: AuthApi, owner: Member
) -> None:
    other = seed_organization(api.owner)
    home = _organization_of(api, owner)
    chosen = str(uuid4())
    foreign = {
        "organizationId": str(other.org),
        "organization_id": str(other.org),
        "builtIn": True,
        "built_in": True,
    }

    role = ok(
        await api.client.post(
            ROLES,
            json={
                "name": "Night clerk",
                "permissions": ["revenue.view"],
                "id": chosen,
                "version": 7,
            }
            | foreign,
            headers=owner.headers,
        )
    )
    decoy = await _create(api, owner, "Day clerk", ["revenue.view"])
    changed = ok(
        await api.client.put(
            f"{ROLES}/{role['id']}",
            json={"name": "Night shift", "permissions": ["revenue.view"], "version": 1}
            | {"id": decoy["id"]}
            | foreign,
            headers=owner.headers,
        )
    )

    assert role["id"] != chosen and (role["builtIn"], role["version"]) == (False, 1)
    assert _organization_of_role(api, chosen) is None
    assert (changed["id"], changed["name"], changed["builtIn"], changed["version"]) == (
        role["id"],
        "Night shift",
        False,
        2,
    )
    roles = await _roles(api, owner)
    assert roles["Day clerk"] == decoy
    assert home != other.org
    assert {_organization_of_role(api, r["id"]) for r in roles.values()} == {home}


async def test_a_blocked_member_is_refused_on_every_route(
    api: AuthApi, owner: Member, admin: Member
) -> None:
    role = await _create(api, owner, "Night clerk", ["revenue.view"])
    person = await invite(api, owner)
    version = ok(await api.client.get(f"{PEOPLE}/{admin.user_id}", headers=owner.headers))[
        "version"
    ]
    ok(
        await api.client.post(
            f"{PEOPLE}/{admin.user_id}/deactivate",
            json={"version": version, "reason": "Left the company"},
            headers=owner.headers,
        )
    )

    for response in await _five_routes(api, admin.headers, role["id"], person):
        empty(response, 401)
    _untouched(api, role, person)


async def test_a_member_whose_membership_ended_is_refused_while_their_session_lives(
    api: AuthApi, owner: Member, admin: Member
) -> None:
    role = await _create(api, owner, "Night clerk", ["revenue.view"])
    person = await invite(api, owner)
    api.owner.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (admin.user_id,)
    )

    for response in await _five_routes(api, admin.headers, role["id"], person):
        problem(response, 403, FORBIDDEN)
    _untouched(api, role, person)


async def test_an_expired_token_is_refused_on_every_route(
    api: AuthApi, owner: Member, admin: Member
) -> None:
    role = await _create(api, owner, "Night clerk", ["revenue.view"])
    person = await invite(api, owner)
    api.clock.advance(600)

    for response in await _five_routes(api, admin.headers, role["id"], person):
        empty(response, 401)
    _untouched(api, role, person)


async def test_other_methods_an_override_header_and_a_delete_shaped_body_never_delete(
    api: AuthApi, owner: Member
) -> None:
    role = await _create(api, owner, "Night clerk", ["revenue.view"])
    person = await invite(api, owner)
    person_path, role_path = f"{PEOPLE}/{person}", f"{ROLES}/{role['id']}"
    override = {**owner.headers, "X-HTTP-Method-Override": "DELETE"}

    for method, path, headers in (
        ("PATCH", person_path, owner.headers),
        ("PATCH", role_path, owner.headers),
        ("POST", person_path, override),
        ("POST", role_path, override),
        ("DELETE", PEOPLE, owner.headers),
        ("DELETE", ROLES, owner.headers),
    ):
        response = await api.client.request(method, path, headers=headers)
        assert response.status_code == 405, (method, path, response.content)
    version = ok(await api.client.get(person_path, headers=owner.headers))["version"]
    shaped = {"version": version, "deleted": True, "active": False}
    response = await api.client.put(person_path, json=shaped, headers=owner.headers)

    assert response.status_code == 400, response.content
    assert ok(await api.client.get(person_path, headers=owner.headers))["version"] == version
    _untouched(api, role, person)


@pytest.mark.parametrize("key", ["people.add", "people.sign_in"])
async def test_deleting_a_person_needs_the_block_permission_as_erasing_does(
    api: AuthApi, owner: Member, admin: Member, key: str
) -> None:
    role = await _create(api, owner, "People desk", [key])
    _give(api, admin, role["id"])
    person = await invite(api, owner)

    problem(await api.client.delete(f"{PEOPLE}/{person}", headers=admin.headers), 403, FORBIDDEN)
    assert _person_exists(api, person)


async def test_a_block_holder_deletes_a_person_but_not_an_owner_or_themselves(
    api: AuthApi, owner: Member, admin: Member
) -> None:
    role = await _create(api, owner, "Door keeper", ["people.block"])
    _give(api, admin, role["id"])
    person = await invite(api, owner)

    for target, sentence in ((owner.user_id, OWNER_EDIT), (admin.user_id, SELF)):
        problem(
            await api.client.delete(f"{PEOPLE}/{target}", headers=admin.headers),
            403,
            FORBIDDEN,
            sentence,
        )
        assert _person_exists(api, target)
    assert ok(await api.client.delete(f"{PEOPLE}/{person}", headers=admin.headers)) == {
        "id": person
    }
    assert not _person_exists(api, person)
