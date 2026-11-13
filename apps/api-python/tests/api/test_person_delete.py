"""``DELETE /setup/people/{id}`` against the real database: a person nothing refers to answers
``{id}`` in two statements, goes with their account and pending invitation, and leaves a
history line without their email or mobile number, which their earlier history loses too; a
second delete is not found. A person who
signed in has records and answers 409 with the sentence that says what to do instead, and
stays. A caller without ``people.manage`` and oneself get 403, a non-Owner on an Owner 403,
another organization's person 404, a malformed id an empty 404 and no token 401."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest

from xcode_api.http.messages import IN_USE_TITLE

from ..support.client import ApiFactory, AuthApi
from ..support.fakes import role_rights
from ..support.rows import seed_organization
from ..support.setup_client import (
    FORBIDDEN,
    NOT_FOUND,
    Member,
    empty,
    join,
    ok,
    problem,
    statements,
)
from .test_invitations import PERSON_EMAIL, PERSON_PHONE, invite

pytestmark = pytest.mark.asyncio(loop_scope="session")

IN_USE = "Jane Doe has records: block them instead, and erase their details if those must go."
SELF = "You cannot delete yourself."
OWNER_EDIT = "Only an Owner can change, remove or sign out an Owner."


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


@pytest.fixture
async def clerk(api: AuthApi, owner: Member) -> Member:
    return await join(api, email="cleo@example.com", phone="0733000111", role="Revenue clerk")


def _path(user_id: object) -> str:
    return f"/setup/people/{user_id}"


async def _delete(api: AuthApi, member: Member, user_id: object) -> tuple[httpx.Response, int]:
    return await statements(api.client.delete(_path(user_id), headers=member.headers))


def _rows(api: AuthApi, user_id: object) -> dict[str, int]:
    row = api.owner.execute(
        "SELECT (SELECT count(*) FROM identity.users WHERE id = %(u)s) AS users, "
        "(SELECT count(*) FROM tenancy.memberships WHERE user_id = %(u)s) AS memberships, "
        "(SELECT count(*) FROM identity.invitations WHERE user_id = %(u)s) AS invitations",
        {"u": user_id},
    ).fetchone()
    assert row is not None
    return {key: int(value) for key, value in row.items()}


def _exists(api: AuthApi, user_id: object) -> bool:
    rows = _rows(api, user_id)
    return rows["users"] == 1 and rows["memberships"] >= 1


async def _history_of(api: AuthApi, member: Member, user_id: object) -> list[dict[str, Any]]:
    page = ok(
        await api.client.get("/setup/history?section=people&pageSize=100", headers=member.headers)
    )
    return [e for e in page["items"] if e["entityId"] == str(user_id)]


async def test_a_person_nothing_refers_to_is_deleted_and_logged_without_contact_details(
    api: AuthApi, owner: Member
) -> None:
    person = await invite(api, owner)
    assert _rows(api, person) == {"users": 1, "memberships": 1, "invitations": 1}

    response, count = await _delete(api, owner, person)

    assert ok(response) == {"id": person}
    assert count == 2
    assert _rows(api, person) == {"users": 0, "memberships": 0, "invitations": 0}
    entries = await _history_of(api, owner, person)
    entry = entries[0]
    assert entry["reason"] == "Deleted Jane Njeri"
    assert len(entries) > 1 and json.loads(entries[-1]["after"])["FirstName"] == "Jane"
    for earlier in entries:
        text = f"{earlier['before']} {earlier['after']}"
        assert PERSON_EMAIL not in text and PERSON_PHONE[1:] not in text
    assert entry["after"] == "null"
    before = json.loads(entry["before"])
    assert (before["FirstName"], before["LastName"]) == ("Jane", "Njeri")
    assert (before["Email"], before["PhoneNumber"]) == (None, None)
    assert PERSON_EMAIL not in entry["before"] and PERSON_PHONE[1:] not in entry["before"]
    problem((await _delete(api, owner, person))[0], 404, NOT_FOUND)
    problem(await api.client.get(_path(person), headers=owner.headers), 404, NOT_FOUND)


async def test_a_person_with_records_answers_409_with_the_sentence_and_stays(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    response, count = await _delete(api, owner, clerk.user_id)

    body = problem(response, 409, IN_USE_TITLE, IN_USE)
    assert "use" not in body and "name" not in body
    assert count == 1
    assert _exists(api, clerk.user_id)


async def test_a_caller_without_people_manage_and_oneself_are_refused(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    person = await invite(api, owner)
    for target in (person, uuid4(), owner.user_id):
        response, count = await _delete(api, clerk, target)
        problem(response, 403, FORBIDDEN)
        assert count == 1
    response, count = await _delete(api, owner, owner.user_id)
    problem(response, 403, FORBIDDEN, SELF)
    assert count == 1
    assert _exists(api, person) and _exists(api, owner.user_id)


async def test_only_an_owner_may_delete_an_owner(api: AuthApi, owner: Member) -> None:
    second = await invite(api, owner, role="Owner", permissions=list(role_rights("Owner")))
    admin = await join(api, email="admin@example.com", phone="0744000111", role="Office admin")

    problem((await _delete(api, admin, second))[0], 403, FORBIDDEN, OWNER_EDIT)
    assert _exists(api, second)
    assert ok((await _delete(api, owner, second))[0]) == {"id": second}
    assert not _exists(api, second)


async def test_another_organizations_person_is_not_found_and_stays(
    api: AuthApi, owner: Member
) -> None:
    other = seed_organization(api.owner)
    for target in (other.user2, other.user):
        problem((await _delete(api, owner, target))[0], 404, NOT_FOUND)
        assert _exists(api, target)


async def test_a_malformed_id_is_an_empty_404_and_no_token_is_401(
    api: AuthApi, owner: Member
) -> None:
    person = await invite(api, owner)
    for malformed in ("not-a-uuid", "1' OR '1'='1"):
        empty(await api.client.delete(_path(malformed), headers=owner.headers), 404)
    empty(await api.client.delete(_path(person)), 401)
    assert _exists(api, person)
