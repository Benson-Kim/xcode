"""``POST /setup/people/{id}/erasure`` against the real database (row S59): a blocked person's
name, email and mobile number leave this organization and its history, after which they are
404 and off the list; a repeat answers the same; oneself, an active person, a stale version,
a missing reason or version, a caller without ``people.block``, a non-Owner on an Owner and
another organization's person are refused with nothing erased."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ..support.client import ApiFactory, AuthApi
from ..support.fakes import role_rights
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
)
from .test_invitations import invite

pytestmark = pytest.mark.asyncio(loop_scope="session")

OWNER_EDIT = "Only an Owner can change, remove or sign out an Owner."
REASON = "Asked for their account to be deleted"


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
    return f"/setup/people/{user_id}/erasure"


async def _block(api: AuthApi, owner: Member, user_id: object) -> None:
    ok(
        await api.client.post(
            f"/setup/people/{user_id}/deactivate",
            json={"version": 1, "reason": "Asked to leave"},
            headers=owner.headers,
        )
    )


def _account(api: AuthApi, user_id: object) -> dict[str, Any]:
    row = api.owner.execute(
        "SELECT u.email, u.phone_number, u.pin_hash, u.erased_at, m.first_name, m.last_name "
        "FROM identity.users AS u JOIN tenancy.memberships AS m ON m.user_id = u.id "
        "WHERE u.id = %s",
        (user_id,),
    ).fetchone()
    assert row is not None
    return dict(row)


def _untouched(api: AuthApi, user_id: object) -> None:
    account = _account(api, user_id)
    assert account["erased_at"] is None
    assert account["email"] is not None and account["phone_number"] is not None


async def _history_of(api: AuthApi, member: Member, user_id: object) -> list[dict[str, Any]]:
    page = ok(await api.client.get("/setup/history?section=people", headers=member.headers))
    return [e for e in page["items"] if e["entityId"] == str(user_id)]


async def test_a_blocked_person_is_erased_then_not_found_and_off_the_list(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    await _block(api, owner, clerk.user_id)
    body = {"version": 2, "reason": REASON}
    answer = await api.client.post(_path(clerk.user_id), json=body, headers=owner.headers)
    assert ok(answer) == {"id": str(clerk.user_id)}
    account = _account(api, clerk.user_id)
    assert account["erased_at"] is not None
    assert (account["email"], account["phone_number"], account["pin_hash"]) == (None, None, None)
    assert (account["first_name"], account["last_name"]) == ("Former", "member")
    problem(
        await api.client.get(f"/setup/people/{clerk.user_id}", headers=owner.headers),
        404,
        NOT_FOUND,
    )
    listed = ok(await api.client.get("/setup/people?page=1&pageSize=100", headers=owner.headers))
    assert str(clerk.user_id) not in {item["id"] for item in listed["items"]}
    entries = await _history_of(api, owner, clerk.user_id)
    erased = f"Erased the personal details of a former member. Reason: {REASON}."
    assert entries[0]["reason"] == erased
    for entry in entries:
        text = json.dumps([entry["reason"], entry.get("before"), entry.get("after")])
        assert "cleo@example.com" not in text and "0733000111" not in text
        assert "Jane Doe" not in text
    again = await api.client.post(_path(clerk.user_id), json=body, headers=owner.headers)
    assert ok(again) == {"id": str(clerk.user_id)}
    assert len(await _history_of(api, owner, clerk.user_id)) == len(entries)


async def test_oneself_and_an_active_person_are_refused(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    problem(
        await api.client.post(
            _path(owner.user_id), json={"version": 1, "reason": REASON}, headers=owner.headers
        ),
        400,
        INVALID,
        "You cannot erase your own details here.",
    )
    problem(
        await api.client.post(
            _path(clerk.user_id), json={"version": 1, "reason": REASON}, headers=owner.headers
        ),
        400,
        INVALID,
        "Block this person before erasing their details.",
    )
    _untouched(api, owner.user_id)
    _untouched(api, clerk.user_id)


async def test_a_stale_version_a_missing_reason_or_version_erase_nothing(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    await _block(api, owner, clerk.user_id)
    path = _path(clerk.user_id)
    problem(
        await api.client.post(path, json={"version": 1, "reason": REASON}, headers=owner.headers),
        409,
        STALE,
    )
    problem(
        await api.client.post(path, json={"version": 2}, headers=owner.headers),
        400,
        INVALID,
        "A reason of 1\u2013500 characters is required.",
    )
    missing = await api.client.post(path, json={"reason": REASON}, headers=owner.headers)
    body = problem(missing, 400, INVALID, missing.json().get("detail"))
    assert list(body["errors"]) == ["version"]
    empty(await api.client.post(path, headers=owner.headers), 415)
    _untouched(api, clerk.user_id)


async def test_erasure_needs_people_block_and_an_owner_for_an_owner(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    second = await invite(api, owner, role="Owner", permissions=list(role_rights("Owner")))
    admin = await join(api, email="admin@example.com", phone="0744000111", role="Office admin")
    await _block(api, owner, second)
    body = {"version": 2, "reason": REASON}
    problem(await api.client.post(_path(second), json=body, headers=clerk.headers), 403, FORBIDDEN)
    problem(
        await api.client.post(_path(second), json=body, headers=admin.headers),
        403,
        FORBIDDEN,
        OWNER_EDIT,
    )
    _untouched(api, second)
    assert ok(await api.client.post(_path(second), json=body, headers=owner.headers)) == {
        "id": second
    }


async def test_another_organizations_person_is_not_found_and_keeps_their_details(
    api: AuthApi, owner: Member
) -> None:
    other = seed_organization(api.owner)
    problem(
        await api.client.post(
            _path(other.user2), json={"version": 1, "reason": REASON}, headers=owner.headers
        ),
        404,
        NOT_FOUND,
    )
    account = api.owner.execute(
        "SELECT email, erased_at FROM identity.users WHERE id = %s", (other.user2,)
    ).fetchone()
    assert account is not None
    assert account["erased_at"] is None and account["email"] is not None


async def test_an_anonymous_caller_gets_the_uniform_401(api: AuthApi, clerk: Member) -> None:
    response = await api.client.post(_path(clerk.user_id), json={"version": 1, "reason": REASON})
    assert response.status_code == 401
