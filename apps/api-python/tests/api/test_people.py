"""The people routes against the real database (``docs/06-http-contract.md`` section 2.2):
the person document in wire order, paging, create and update with their refusals and exact
sentences, the lifecycle routes with the optional body, the sign-in actions (make them reset
the PIN, remove one device, remove all), the back-dating limit, the statuses, 415 and the
non-UUID 404, the statement budget, and the session side effects seen through
``/auth/session`` and ``/auth/refresh``."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import pytest

from ..support.client import ApiFactory, AuthApi, envelope
from ..support.fakes import role_rights
from ..support.scenario import PIN_HASH, set_user
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
from ..support.tenancy import add_company, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

PERSON_KEYS = [
    "id",
    "firstName",
    "lastName",
    "email",
    "phoneNumber",
    "role",
    "active",
    "scopeMode",
    "companyIds",
    "vehicleIds",
    "permissions",
    "approvalLimit",
    "hasPin",
    "version",
    "otherCompanies",
    "otherVehicles",
    "status",
    "lastSignedInAt",
    "backLimit",
    "canChange",
    "modules",
    "everything",
]
PERSON_DETAIL_KEYS = [*PERSON_KEYS, "signIn"]


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


def person(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "firstName": "Jane",
        "lastName": "Njeri",
        "email": "jane.njeri@example.com",
        "phoneNumber": "0722000111",
        "role": "Revenue clerk",
        "scopeMode": "all",
        "companyIds": [],
        "vehicleIds": [],
        "permissions": list(role_rights("Revenue clerk")),
        "approvalLimit": None,
    }
    body.update(changes)
    return body


async def create(api: AuthApi, member: Member, **changes: Any) -> str:
    body = ok(
        await api.client.post("/setup/people", json=person(**changes), headers=member.headers)
    )
    assert list(body) == ["id"]
    return str(body["id"])


async def test_a_created_person_reads_back_in_the_wire_order(api: AuthApi, owner: Member) -> None:
    response, count = await statements(
        api.client.post("/setup/people", json=person(), headers=owner.headers)
    )
    created = ok(response)
    assert count == 3, "the third statement asks whether an invitation is due for mailing"
    response, count = await statements(
        api.client.get(f"/setup/people/{created['id']}", headers=owner.headers)
    )
    body = ok(response)
    assert count == 2
    assert list(body) == PERSON_DETAIL_KEYS
    assert body["id"] == created["id"]
    assert (body["firstName"], body["phoneNumber"], body["role"]) == (
        "Jane",
        "+254722000111",
        "Revenue clerk",
    )
    assert (body["active"], body["hasPin"], body["version"], body["approvalLimit"]) == (
        True,
        False,
        1,
        None,
    )
    assert body["scopeMode"] == "all"
    assert body["permissions"] == list(role_rights("Revenue clerk"))
    assert (body["status"], body["lastSignedInAt"], body["canChange"]) == (
        "invited",
        None,
        "7 days back",
    )
    assert body["backLimit"] == {"mode": "days", "count": 7, "from": None}
    assert body["modules"] == [
        {"name": "Dashboard", "held": 1, "total": 3},
        {"name": "Revenue", "held": 2, "total": 4},
    ]
    assert body["everything"] is False
    sign_in = body["signIn"]
    assert list(sign_in) == ["status", "lock", "lastSignedInAt", "email", "invitation", "devices"]
    invitation = sign_in.pop("invitation")
    assert sorted(invitation) == ["expiresAt", "sentAt", "state"]
    assert invitation["state"] in ("pending", "sent") and invitation["expiresAt"] is not None
    assert sign_in == {
        "status": "invited",
        "lock": None,
        "lastSignedInAt": None,
        "email": "jane.njeri@example.com",
        "devices": [],
    }


async def test_the_people_page_carries_its_paging_fields(api: AuthApi, owner: Member) -> None:
    await create(api, owner)
    response, count = await statements(
        api.client.get("/setup/people?page=1&pageSize=1", headers=owner.headers)
    )
    page = ok(response)
    assert count == 2
    assert list(page) == ["items", "pageNumber", "pageSize", "total"]
    assert (page["pageNumber"], page["pageSize"], page["total"]) == (1, 1, 2)
    assert list(page["items"][0]) == PERSON_KEYS
    for query in ("page=0", "pageSize=101", "page=100001", "pageSize=0"):
        problem(
            await api.client.get(f"/setup/people?{query}", headers=owner.headers),
            400,
            INVALID,
            "Page must be 1\u2013100000 and page size 1\u2013100.",
        )
    unparsable = await api.client.get("/setup/people?page=one", headers=owner.headers)
    assert unparsable.status_code == 400


async def one_of_each_state(api: AuthApi, owner: Member) -> tuple[str, str, str]:
    """An invited person (just added), one not signed in with no live invitation (deactivating
    ends it, reactivating sends none) and a blocked one."""
    invited = await create(api, owner)
    waiting = await create(api, owner, email="wanjiru@example.com", phoneNumber="0722000113")
    off = await create(api, owner, email="otieno@example.com", phoneNumber="0722000112")
    deactivate = {"version": 1, "reason": "Left the company"}
    for person_id in (waiting, off):
        ok(
            await api.client.post(
                f"/setup/people/{person_id}/deactivate", json=deactivate, headers=owner.headers
            )
        )
    ok(
        await api.client.post(
            f"/setup/people/{waiting}/activate", json={"version": 2}, headers=owner.headers
        )
    )
    return invited, waiting, off


async def test_the_people_page_keeps_one_role_and_one_sign_in_state(
    api: AuthApi, owner: Member
) -> None:
    invited, waiting, off = await one_of_each_state(api, owner)

    async def ids(query: str) -> list[str]:
        response, count = await statements(
            api.client.get(f"/setup/people?pageSize=100{query}", headers=owner.headers)
        )
        assert count == 2
        return [item["id"] for item in ok(response)["items"]]

    assert await ids("&status=invited") == [invited]
    assert await ids("&status=waiting") == [waiting]
    assert await ids("&status=none") == [off]
    assert await ids("&status=active") == [str(owner.user_id)]
    assert await ids("&role=Revenue%20clerk") == sorted([invited, waiting, off])
    assert await ids("&role=Revenue%20clerk&status=none") == [off]
    assert await ids("&role=all&status=all") == await ids("")
    assert await ids("&role=Driver") == []
    problem(
        await api.client.get("/setup/people?status=asleep", headers=owner.headers),
        400,
        INVALID,
        "Status must be active, not_signed_in, invited, invite_expired, pin_reset_due,"
        " locked or blocked.",
    )


async def test_the_status_filter_accepts_the_new_and_the_legacy_words(
    api: AuthApi, owner: Member
) -> None:
    invited, waiting, off = await one_of_each_state(api, owner)

    async def ids(status: str) -> list[str]:
        page = ok(
            await api.client.get(
                f"/setup/people?pageSize=100&status={status}", headers=owner.headers
            )
        )
        return [item["id"] for item in page["items"]]

    assert await ids("not_signed_in") == await ids("waiting") == [waiting]
    assert await ids("blocked") == await ids("none") == [off]
    assert await ids("invited") == [invited]
    assert await ids("active") == [str(owner.user_id)]
    assert await ids("pin_reset_due") == await ids("locked") == await ids("invite_expired") == []


@pytest.mark.parametrize(
    ("changes", "status", "detail"),
    [
        ({"firstName": " "}, 400, "First and last name are required."),
        ({"email": "nobody"}, 400, "A valid email is required."),
        ({"phoneNumber": "12"}, 400, "A valid mobile number is required."),
        ({"scopeMode": "everything"}, 400, "Choose a data scope."),
        ({"scopeMode": "companies"}, 400, "Choose at least one item in the data scope."),
        ({"permissions": []}, 400, "Permissions and approval limit are invalid."),
        ({"role": "Driver"}, 400, "Unknown role."),
        ({"permissions": ["revenue.view", "no.such_key"]}, 400, "Unknown permission."),
    ],
)
async def test_a_malformed_person_is_refused_with_its_sentence(
    api: AuthApi, owner: Member, changes: dict[str, Any], status: int, detail: str
) -> None:
    response = await api.client.post("/setup/people", json=person(**changes), headers=owner.headers)
    problem(response, status, INVALID, detail)


async def test_a_vehicle_scope_may_be_empty_and_a_company_scope_may_not(
    api: AuthApi, owner: Member
) -> None:
    person_id = await create(api, owner, scopeMode="vehicles")
    path = f"/setup/people/{person_id}"
    body = ok(await api.client.get(path, headers=owner.headers))
    assert (body["scopeMode"], body["companyIds"], body["vehicleIds"]) == ("vehicles", [], [])
    refused = await api.client.put(
        path, json=person(scopeMode="companies", version=1), headers=owner.headers
    )
    problem(refused, 400, INVALID, "Choose at least one item in the data scope.")
    ok(await api.client.put(path, json=person(version=1), headers=owner.headers))
    emptied = person(scopeMode="vehicles", version=2)
    ok(await api.client.put(path, json=emptied, headers=owner.headers))
    body = ok(await api.client.get(path, headers=owner.headers))
    assert (body["scopeMode"], body["companyIds"], body["vehicleIds"], body["version"]) == (
        "vehicles",
        [],
        [],
        3,
    )


async def test_only_an_editor_who_sees_every_company_may_leave_the_vehicle_list_empty(
    api: AuthApi, owner: Member
) -> None:
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    org = UUID(str(row["id"]))
    alpha = add_company(api.owner, org, "Alpha Sacco")
    office = await join(api, email="otto@example.com", phone="0733000111", role="Office admin")
    scoped = await join(api, email="sam@example.com", phone="0733000222", role="Office admin")
    set_scope(api.owner, scoped.user_id, org, companies=[alpha])
    person_id = await create(api, owner, scopeMode="companies", companyIds=[str(alpha)])
    path = f"/setup/people/{person_id}"
    no_vehicles = person(
        email="mary@example.com",
        phoneNumber="0722000222",
        role="Office admin",
        permissions=list(role_rights("Office admin")),
        scopeMode="vehicles",
    )
    sentence = "Choose at least one item in the data scope."
    refused = await api.client.post("/setup/people", json=no_vehicles, headers=scoped.headers)
    problem(refused, 400, INVALID, sentence)
    emptied = person(scopeMode="vehicles", version=1)
    refused = await api.client.put(path, json=emptied, headers=scoped.headers)
    problem(refused, 400, INVALID, sentence)
    created = ok(await api.client.post("/setup/people", json=no_vehicles, headers=office.headers))
    body = ok(await api.client.get(f"/setup/people/{created['id']}", headers=office.headers))
    assert (body["scopeMode"], body["companyIds"], body["vehicleIds"]) == ("vehicles", [], [])
    body = ok(await api.client.get(path, headers=owner.headers))
    assert (body["scopeMode"], body["companyIds"], body["version"]) == (
        "companies",
        [str(alpha)],
        1,
    )


async def test_contact_details_already_in_use_are_refused(api: AuthApi, owner: Member) -> None:
    await create(api, owner)
    response = await api.client.post(
        "/setup/people", json=person(phoneNumber="0733000222"), headers=owner.headers
    )
    problem(response, 400, INVALID, "That mobile number or email already belongs to someone.")


async def test_only_an_owner_gives_the_owner_role(api: AuthApi, owner: Member) -> None:
    admin = await join(api, email="admin@example.com", phone="0744000111", role="Office admin")
    refused = await api.client.post(
        "/setup/people",
        json=person(role="Owner", permissions=list(role_rights("Owner"))),
        headers=admin.headers,
    )
    problem(refused, 403, FORBIDDEN, "Only an Owner can give the Owner role.")
    clerk_with_less = await api.client.post(
        "/setup/people", json=person(role="Fleet manager"), headers=admin.headers
    )
    problem(clerk_with_less, 403, FORBIDDEN, "You can only grant roles whose permissions you hold.")


async def test_an_update_needs_the_loaded_version(api: AuthApi, owner: Member) -> None:
    person_id = await create(api, owner)
    path = f"/setup/people/{person_id}"
    problem(
        await api.client.put(path, json=person(), headers=owner.headers),
        400,
        INVALID,
        "Reload this person before saving.",
    )
    renamed = person(firstName="Janet", version=1)
    response, count = await statements(api.client.put(path, json=renamed, headers=owner.headers))
    assert ok(response) == {"id": person_id}
    assert count == 4, (
        "the third statement asks whether an invitation is due for mailing, "
        "the fourth claims the sign-in notices the change wrote"
    )
    problem(await api.client.put(path, json=renamed, headers=owner.headers), 409, STALE)
    assert ok(await api.client.get(path, headers=owner.headers))["version"] == 2


async def _sign_in_mails(api: AuthApi, count: int) -> list[tuple[str, str]]:
    for _ in range(500):
        mails = [m for m in api.mail.sent if m.tags.get("purpose") == "sign_in_change"]
        if len(mails) >= count:
            return sorted((m.tags["kind"], m.to) for m in mails)
        await asyncio.sleep(0.01)
    raise AssertionError(f"expected {count} sign-in notices")


async def _create_with_pin(api: AuthApi, owner: Member) -> str:
    person_id = await create(api, owner)
    set_user(api.owner, UUID(person_id), pin_hash=PIN_HASH)
    return person_id


async def test_a_new_sign_in_email_is_told_to_the_old_and_the_new_address(
    api: AuthApi, owner: Member
) -> None:
    person_id = await _create_with_pin(api, owner)
    changed = person(email="janet.njeri@example.com", version=1)
    ok(await api.client.put(f"/setup/people/{person_id}", json=changed, headers=owner.headers))
    assert await _sign_in_mails(api, 2) == [
        ("new", "janet.njeri@example.com"),
        ("old", "jane.njeri@example.com"),
    ]
    (old,) = [m for m in api.mail.sent if m.tags.get("kind") == "old"]
    assert "It is now j***@example.com." in old.text


async def test_a_new_mobile_number_is_told_to_the_current_address(
    api: AuthApi, owner: Member
) -> None:
    person_id = await _create_with_pin(api, owner)
    changed = person(phoneNumber="0722000999", version=1)
    ok(await api.client.put(f"/setup/people/{person_id}", json=changed, headers=owner.headers))
    assert await _sign_in_mails(api, 1) == [("current", "jane.njeri@example.com")]


async def test_editing_yourself_is_refused(api: AuthApi, owner: Member) -> None:
    response = await api.client.put(
        f"/setup/people/{owner.user_id}",
        json=person(
            email="ann@example.com",
            phoneNumber="0711000111",
            role="Owner",
            permissions=list(role_rights("Owner")),
            version=1,
        ),
        headers=owner.headers,
    )
    problem(response, 400, INVALID, "You cannot change your own access here.")


async def test_bodyless_lifecycle_calls_ask_for_a_reload(api: AuthApi, owner: Member) -> None:
    person_id = await create(api, owner)
    for action in ("deactivate", "activate"):
        response = await api.client.post(
            f"/setup/people/{person_id}/{action}", headers=owner.headers
        )
        if action == "deactivate":
            problem(response, 409, STALE)
        else:
            assert ok(response) == {"id": person_id}
    empty_body = await api.client.post(
        f"/setup/people/{person_id}/deactivate", content=b"", headers=owner.headers
    )
    problem(empty_body, 409, STALE)
    assert ok(await api.client.get(f"/setup/people/{person_id}", headers=owner.headers))["active"]


async def test_deactivation_needs_a_reason_and_repeats_harmlessly(
    api: AuthApi, owner: Member
) -> None:
    person_id = await create(api, owner)
    path = f"/setup/people/{person_id}/deactivate"
    problem(
        await api.client.post(path, json={"version": 1}, headers=owner.headers),
        400,
        INVALID,
        "A reason of 1\u2013500 characters is required.",
    )
    body = {"version": 1, "reason": "Left the organization"}
    response, count = await statements(api.client.post(path, json=body, headers=owner.headers))
    assert ok(response) == {"id": person_id}
    assert count == 2
    assert ok(await api.client.post(path, json={}, headers=owner.headers)) == {"id": person_id}
    restored = await api.client.post(
        f"/setup/people/{person_id}/activate", json={"version": 2}, headers=owner.headers
    )
    assert ok(restored) == {"id": person_id}


async def test_self_lifecycle_and_sign_out_are_refused(api: AuthApi, owner: Member) -> None:
    base = f"/setup/people/{owner.user_id}"
    problem(
        await api.client.post(
            f"{base}/deactivate", json={"version": 1, "reason": "x"}, headers=owner.headers
        ),
        400,
        INVALID,
        "You cannot deactivate your own access.",
    )
    problem(
        await api.client.post(f"{base}/sign-out", headers=owner.headers),
        400,
        INVALID,
        "Use sign out for your own session.",
    )
    problem(
        await api.client.post(f"{base}/pin-reset", headers=owner.headers),
        400,
        INVALID,
        "Use the profile menu for your own PIN and devices.",
    )
    device = "00000000-0000-4000-8000-000000000000"
    problem(
        await api.client.post(f"{base}/trusted-devices/{device}/remove", headers=owner.headers),
        400,
        INVALID,
        "Use the profile menu for your own PIN and devices.",
    )


async def test_an_unknown_or_malformed_id_is_not_found(api: AuthApi, owner: Member) -> None:
    unknown = "00000000-0000-4000-8000-000000000000"
    problem(await api.client.get(f"/setup/people/{unknown}", headers=owner.headers), 404, NOT_FOUND)
    empty(await api.client.get("/setup/people/not-a-uuid", headers=owner.headers), 404)
    empty(await api.client.post("/setup/people/not-a-uuid/sign-out", headers=owner.headers), 404)
    empty(await api.client.post("/setup/people/not-a-uuid/pin-reset", headers=owner.headers), 404)
    malformed_device = f"/setup/people/{owner.user_id}/trusted-devices/not-a-uuid/remove"
    empty(await api.client.post(malformed_device, headers=owner.headers), 404)
    problem(
        await api.client.post(f"/setup/people/{unknown}/pin-reset", headers=owner.headers),
        404,
        NOT_FOUND,
    )


async def test_a_body_route_without_json_is_415(api: AuthApi, owner: Member) -> None:
    payload = json.dumps(person()).encode()
    text = await api.client.post(
        "/setup/people",
        content=payload,
        headers={**owner.headers, "Content-Type": "text/plain"},
    )
    empty(text, 415)
    missing = await api.client.post("/setup/people", content=payload, headers=owner.headers)
    empty(missing, 415)
    wrong = await api.client.post(
        f"/setup/people/{owner.user_id}/deactivate",
        content=b'{"version": 1}',
        headers={**owner.headers, "Content-Type": "text/plain"},
    )
    empty(wrong, 415)
    malformed = await api.client.post(
        "/setup/people",
        content=b"{not json",
        headers={**owner.headers, "Content-Type": "application/json"},
    )
    assert malformed.status_code == 400


async def test_a_role_change_ends_the_access_token_but_the_refresh_token_renews_it(
    api: AuthApi, owner: Member
) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0722000999", role="Revenue clerk")
    assert (await api.client.get("/auth/session", headers=clerk.headers)).status_code == 200
    update = person(
        email="clerk@example.com",
        phoneNumber="0722000999",
        firstName="Jane",
        lastName="Doe",
        permissions=[*role_rights("Revenue clerk"), "reports.view"],
        version=1,
    )
    ok(await api.client.put(f"/setup/people/{clerk.user_id}", json=update, headers=owner.headers))
    empty(await api.client.get("/auth/session", headers=clerk.headers), 401)
    renewed = envelope(
        await api.post(
            "/auth/refresh", refreshToken=clerk.tokens["refreshToken"], deviceId="device-0999"
        ),
        200,
        "authenticated",
    )
    session = ok(
        await api.client.get(
            "/auth/session", headers={"Authorization": f"Bearer {renewed['accessToken']}"}
        )
    )
    assert "reports.view" in session["permissions"]


async def test_deactivation_ends_sessions_and_refresh(api: AuthApi, owner: Member) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0722000999", role="Revenue clerk")
    body = {"version": 1, "reason": "Left the organization"}
    ok(
        await api.client.post(
            f"/setup/people/{clerk.user_id}/deactivate", json=body, headers=owner.headers
        )
    )
    empty(await api.client.get("/auth/session", headers=clerk.headers), 401)
    envelope(
        await api.post(
            "/auth/refresh", refreshToken=clerk.tokens["refreshToken"], deviceId="device-0999"
        ),
        401,
        "authentication_failed",
    )


async def test_signing_a_person_out_ends_their_sessions(api: AuthApi, owner: Member) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0722000999", role="Revenue clerk")
    response, count = await statements(
        api.client.post(f"/setup/people/{clerk.user_id}/sign-out", headers=owner.headers)
    )
    assert ok(response) == {"id": str(clerk.user_id)}
    assert count == 2
    empty(await api.client.get("/auth/session", headers=clerk.headers), 401)
    envelope(
        await api.post(
            "/auth/refresh", refreshToken=clerk.tokens["refreshToken"], deviceId="device-0999"
        ),
        401,
        "authentication_failed",
    )


async def test_people_routes_need_their_permissions(api: AuthApi, owner: Member) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0722000999", role="Revenue clerk")
    problem(await api.client.get("/setup/people", headers=clerk.headers), 403, FORBIDDEN)
    problem(
        await api.client.post("/setup/people", json=person(), headers=clerk.headers), 403, FORBIDDEN
    )
    base = f"/setup/people/{owner.user_id}"
    device = "00000000-0000-4000-8000-000000000000"
    for path in (
        f"{base}/sign-out",
        f"{base}/pin-reset",
        f"{base}/trusted-devices/{device}/remove",
    ):
        problem(await api.client.post(path, headers=clerk.headers), 403, FORBIDDEN)
    problem(
        await api.client.post(
            f"{base}/deactivate", json={"version": 1, "reason": "x"}, headers=clerk.headers
        ),
        403,
        FORBIDDEN,
    )
    empty(await api.client.get("/setup/people"), 401)


async def _history(api: AuthApi, member: Member, section: str) -> list[dict[str, Any]]:
    page = ok(await api.client.get(f"/setup/history?section={section}", headers=member.headers))
    items: list[dict[str, Any]] = page["items"]
    return items


async def test_remove_all_is_logged_as_trusted_device_removed(api: AuthApi, owner: Member) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0722000999", role="Revenue clerk")
    ok(await api.client.post(f"/setup/people/{clerk.user_id}/sign-out", headers=owner.headers))
    entry = (await _history(api, owner, "signIn"))[0]
    assert entry["reason"] == "Trusted device removed, Jane Doe"
    assert entry["entityId"] == str(clerk.user_id)
    again = await api.client.post(f"/setup/people/{clerk.user_id}/sign-out", headers=owner.headers)
    assert ok(again) == {"id": str(clerk.user_id)}
    removals = [
        e
        for e in await _history(api, owner, "signIn")
        if e["reason"] == "Trusted device removed, Jane Doe"
    ]
    assert len(removals) == 1


async def test_making_a_person_reset_the_pin_ends_their_sessions(
    api: AuthApi, owner: Member
) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0722000999", role="Revenue clerk")
    response, count = await statements(
        api.client.post(f"/setup/people/{clerk.user_id}/pin-reset", headers=owner.headers)
    )
    assert ok(response) == {"id": str(clerk.user_id)}
    assert count == 2
    empty(await api.client.get("/auth/session", headers=clerk.headers), 401)
    envelope(
        await api.post(
            "/auth/refresh", refreshToken=clerk.tokens["refreshToken"], deviceId="device-0999"
        ),
        401,
        "authentication_failed",
    )
    body = ok(await api.client.get(f"/setup/people/{clerk.user_id}", headers=owner.headers))
    assert (body["status"], body["signIn"]["status"], body["signIn"]["devices"]) == (
        "pin_reset_due",
        "pin_reset_due",
        [],
    )
    entry = (await _history(api, owner, "signIn"))[0]
    assert entry["reason"] == "PIN reset required, Jane Doe"


async def test_removing_one_device_ends_only_that_device(api: AuthApi, owner: Member) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0722000999", role="Revenue clerk")
    pane = ok(await api.client.get(f"/setup/people/{clerk.user_id}", headers=owner.headers))[
        "signIn"
    ]
    assert len(pane["devices"]) == 1
    assert list(pane["devices"][0]) == ["id", "name", "trustedAt", "lastUsedAt"]
    device = pane["devices"][0]["id"]
    path = f"/setup/people/{clerk.user_id}/trusted-devices/{device}/remove"
    response, count = await statements(api.client.post(path, headers=owner.headers))
    assert ok(response) == {"id": str(clerk.user_id)}
    assert count == 2
    empty(await api.client.get("/auth/session", headers=clerk.headers), 401)
    problem(await api.client.post(path, headers=owner.headers), 404, NOT_FOUND)
    after = ok(await api.client.get(f"/setup/people/{clerk.user_id}", headers=owner.headers))
    assert after["signIn"]["devices"] == []
    assert after["status"] == "active"


async def test_a_back_limit_is_saved_read_back_and_refused_when_out_of_range(
    api: AuthApi, owner: Member
) -> None:
    limited = person(backLimit={"mode": "months", "count": 1, "from": "2026-09-01"})
    created = ok(await api.client.post("/setup/people", json=limited, headers=owner.headers))
    body = ok(await api.client.get(f"/setup/people/{created['id']}", headers=owner.headers))
    assert body["backLimit"] == {"mode": "months", "count": 1, "from": "2026-09-01"}
    assert body["canChange"] == "1 month back, not before 1 September 2026"
    for back_limit in (
        {"mode": "weeks", "count": 1},
        {"mode": "days", "count": 3651},
        {"mode": "none", "count": 2},
        {"count": 2},
    ):
        problem(
            await api.client.post(
                "/setup/people",
                json=person(email="x@example.com", phoneNumber="0722000555", backLimit=back_limit),
                headers=owner.headers,
            ),
            400,
            INVALID,
            "Choose how far back this person can change records: none, 0 to 3650 days or 0 to "
            "120 months.",
        )
    problem(
        await api.client.post(
            "/setup/people",
            json=person(
                email="y@example.com",
                phoneNumber="0722000556",
                backLimit={"mode": "none", "from": "2999-01-01"},
            ),
            headers=owner.headers,
        ),
        400,
        INVALID,
        "The date before which this person cannot change records cannot be after today.",
    )


async def test_integers_beyond_their_column_types_are_refused_before_the_routine(
    api: AuthApi, owner: Member
) -> None:
    too_many_days = person(backLimit={"mode": "days", "count": 2**31})
    response = await api.client.post("/setup/people", json=too_many_days, headers=owner.headers)
    body = problem(response, 400, INVALID, response.json().get("detail"))
    assert list(body["errors"]) == ["backLimit.count"]
    person_id = await create(api, owner)
    for path, payload in (
        (f"/setup/people/{person_id}", person(version=2**63)),
        (f"/setup/people/{person_id}/deactivate", {"version": 2**63, "reason": "Left"}),
    ):
        call = api.client.put if path.endswith(person_id) else api.client.post
        response = await call(path, json=payload, headers=owner.headers)
        body = problem(response, 400, INVALID, response.json().get("detail"))
        assert list(body["errors"]) == ["version"]
